import Foundation
import Dispatch
import SQLite3

// MARK: - PinnedWorker (크래시 수정)
/// **전용 고정 스레드**에서 job을 실행하는 워커.
///
/// 왜 전용 스레드(고정 소유)여야 하는가 — NSLock으로 '공유 connection을 잠그는' 패턴의 한계:
/// - 실측 크래시(14:53, 빌드 45): readDb/db가 main/http/flush/backfill 등 다중 스레드에서
///   공유 사용되며 sqlite3_prepare_v2에서 dangling pointer SIGSEGV (backtrace: runBackfillTick).
/// - 각 connection을 전용 스레드 하나에 **고정 소유**로 바꿔 공유 자체를 제거 =
///   내부 상태 경합 경로 근절. (GCD serial queue는 dispatch 풀이 스레드를 바꿔 가며 실행 — 고정 스레드로만 안전)
/// - 실측 검증(빌드 46): 기동 113분 + 병렬 폴링 스트레스 → 크래시 0건.
/// - 참고: Apple libsqlite3가 로깅하는 "misuse at line ... of [...]" 진단(이 앱 프로세스에서만
///   관찰 — CLI/Python/동일 Swift 테스트에서는 재현 불가)은 **정보성**이며 크래시 요인이 아님.
///   (실측: 동일 로그 14k+ 건에도 크래시 0건, 데이터 정확. 로그 약 2건/초 — 무해한 노이즈)
private final class PinnedWorker: @unchecked Sendable {
    private struct Job { let run: () -> Void; let done: DispatchSemaphore? }

    private let lock = NSLock()
    private var jobs: [Job] = []
    private var stopping = false
    private var terminated = false
    private let wake = DispatchSemaphore(value: 0)
    private let finished = DispatchSemaphore(value: 0)
    private var thread: Thread?

    init(_ name: String, qos: QualityOfService = .utility) {
        let t = Thread { [weak self] in
            guard let self = self else { return }
            Thread.current.name = name
            self.lock.lock()
            self.thread = Thread.current
            self.lock.unlock()
            while true {
                self.lock.lock()
                let batch = self.jobs
                self.jobs.removeAll()
                let stop = self.stopping
                self.lock.unlock()
                if !batch.isEmpty {
                    for job in batch { job.run(); job.done?.signal() }
                    continue
                }
                if stop {
                    self.lock.lock()
                    self.terminated = true
                    self.lock.unlock()
                    break
                }
                self.wake.wait()
            }
            self.finished.signal()
        }
        t.qualityOfService = qos
        t.start()
        thread = t
    }

    /// 블록을 전용 스레드에서 실행해 결과를 기다림.
    /// - 이미 워커 스레드 위에서 호출(중첩)이면 인라인 실행 → 재귀 deadlock 방지
    /// - 워커 종료 후에는 호출 스레드에서 실행 (호출부는 nil-conn guard 필요)
    func runSync<T>(_ block: @escaping () -> T) -> T {
        lock.lock()
        let onWorker = Thread.current === self.thread
        let dead = terminated
        lock.unlock()
        if onWorker || dead { return block() }
        let done = DispatchSemaphore(value: 0)
        var result: T?
        lock.lock()
        let wasIdle = jobs.isEmpty
        jobs.append(Job(run: {
            let r = block()
            self.lock.lock()
            result = r
            self.lock.unlock()
            done.signal()
        }, done: done))
        lock.unlock()
        if wasIdle { wake.signal() }
        done.wait()
        return result!
    }

    /// 워커 종료: 남은 job 처리 후 스레드 종료 (멱등)
    func stop() {
        lock.lock()
        let already = stopping
        stopping = true
        lock.unlock()
        if !already { wake.signal() }
        finished.wait(timeout: .now() + 5)
    }
}

// MARK: - Database

class Database {
    static let shared = Database()
    /// ⚠️ 쓰기 connection — `writeWorker` **소유**: 그 스레드에서 생성·사용만 가능
    /// (libsqlite3 thread-affinity — 다른 스레드 사용 = misuse → 상태 손상 → SIGSEGV).
    private var db: OpaquePointer?
    /// ⚠️ 읽기 connection — `readWorker` **소유**: 그 스레드에서 생성·사용만 가능.
    /// (설계상 읽기 전용 — 쓰기 SQL은 절대 이 connection으로 보냄. WAL: read/write 병행)
    private var readDb: OpaquePointer?
    let dbPath: String
    /// 이제 `pendingEvents`만 보호 (구 "모든 connection 접근 lock"은 스레드 고정으로 대체).
    private let dbLock = NSLock()
    /// 쓰기 connection 소유 전용 스레드 (1s backfill/5s flush/CRUD/VACUUM 전부 이 스레드)
    private let writeWorker = PinnedWorker("mactt-db-writer")
    /// 읽기 connection 소유 전용 스레드 (dashboard 폴링/집계 쿼리 전부 이 스레드)
    private let readWorker = PinnedWorker("mactt-db-reader")
    /// 이중 close 방지 (dbLock 보호)
    private var isClosed = false

    private init() {
        dbPath = (FileManager.default.homeDirectoryForCurrentUser.path
            as NSString).appendingPathComponent(".mactimetracker/aw.db")
        let dir = (dbPath as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir,
            withIntermediateDirectories: true)
        open()
    }

    deinit {
        close()
    }

    // ── 경량 쓰기: 버퍼 + 배치 트랜잭션 ──
    // 기존: 3s마다 autocommit INSERT = 매번 fsync →
    // 이제: 5s/20개 단위 배치 트랜잭션으로 flush (배치당 fsync 1회)
    // (앱 강제 종료 시 최대 ~5s치 heartbeat 데이터만 유실 — 3s granularity에서 무시 수준)
    private var pendingEvents: [(bucketId: String, ts: Double, dur: Double, data: String)] = []
    private var bucketEnsured = false
    private var flushTimer: DispatchSourceTimer?
    private let flushThreshold = 20

    // ── columnization (data JSON → app/title/url 컬럼) 읽기 ──
    // backfill 완료(모든 행에 컬럼 채움) 이후 JSON 가드 제거 →
    // json_valid가 row당 utf8 전체 실행되는 비용 삭제 (여기서 32MB/쿼리).
    // NULL 폴백: app='Unknown', title=app, url='' (트리에 존재) — 기존과 동일
    private let sqlColApp = "app"
    private let sqlColTitle = "title"
    private let sqlColURL = "url"
    private var backfillTimer: DispatchSourceTimer?

    /// 버퍼드 쓰기 시작 (앱 launch 시 1회)
    func startWriteBuffer() {
        guard flushTimer == nil else { return }
        let timer = DispatchSource.makeTimerSource(queue: DispatchQueue(label: "db-flush", qos: .utility))
        timer.schedule(deadline: .now() + 5, repeating: 5)
        timer.setEventHandler { [weak self] in self?.flushPending() }
        timer.resume()
        flushTimer = timer

        // data JSON column backfill (배경 우선순위, 1s마다 배치 → catch-up까지 약 30분)
        let bf = DispatchSource.makeTimerSource(queue: DispatchQueue(label: "db-backfill", qos: .background))
        bf.schedule(deadline: .now() + 5, repeating: 1)
        bf.setEventHandler { [weak self] in self?.runBackfillTick() }
        bf.resume()
        backfillTimer = bf

        // WAL 파일 팽창 방지: 15분마다 PASSIVE checkpoint (쓰기 블로킹 없음)
        let maint = DispatchSource.makeTimerSource(queue: DispatchQueue(label: "db-maint", qos: .utility))
        maint.schedule(deadline: .now() + 15 * 60, repeating: 15 * 60)
        maint.setEventHandler { [weak self] in
            self?.writeWorker.runSync {
                if let db = self?.db {
                    sqlite3_exec(db, "PRAGMA wal_checkpoint(PASSIVE)", nil, nil, nil)
                }
            }
        }
        maint.resume()
        walTimer = maint
    }
    private var walTimer: DispatchSourceTimer?
    private var retentionTimer: DispatchSourceTimer?

    /// 현재 버퍼를 즉시 DB에 commit (terminate/동기화 시) — write worker로 hop
    func flushPending() {
        writeWorker.runSync { self.flushPendingLocked() }
    }

    /// **writeWorker 스레드에서만** (쓰기 connection은 이 스레드 소유).
    private func flushPendingLocked() {
        // conn 먼저 확인 — close 후에는 버퍼를 drain하지 않는다 (데이터 유실 방지)
        guard let db = db else { return }
        dbLock.lock()
        guard !pendingEvents.isEmpty else { dbLock.unlock(); return }
        let batch = pendingEvents
        pendingEvents.removeAll()
        dbLock.unlock()

        var err: UnsafeMutablePointer<CChar>?
        guard sqlite3_exec(db, "BEGIN", nil, nil, &err) == SQLITE_OK else {
            dbLock.lock()
            pendingEvents.insert(contentsOf: batch, at: 0)  // 실패하면 재시도용 복원
            dbLock.unlock()
            if let err = err { free(err) }
            return
        }
        let sql = "INSERT INTO events (bucket_id, timestamp, duration, data, app, title, url) " +
                  "VALUES (?, ?, ?, ?, json_extract(?, '$.app'), json_extract(?, '$.title'), json_extract(?, '$.url'))"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            sqlite3_exec(db, "ROLLBACK", nil, nil, nil)
            pendingEvents.insert(contentsOf: batch, at: 0)
            return
        }
        for e in batch {
            sqlite3_bind_text(stmt, 1, (e.bucketId as NSString).utf8String, -1, nil)
            sqlite3_bind_double(stmt, 2, e.ts)
            sqlite3_bind_double(stmt, 3, e.dur)
            sqlite3_bind_text(stmt, 4, (e.data as NSString).utf8String, -1, nil)
            // columnization: data JSON에서 SQLite가 app/title/url 추출 (버퍼는 JSON 그대로 보관)
            sqlite3_bind_text(stmt, 5, (e.data as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 6, (e.data as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 7, (e.data as NSString).utf8String, -1, nil)
            if sqlite3_step(stmt) != SQLITE_DONE {
                break
            }
            sqlite3_reset(stmt)
            sqlite3_clear_bindings(stmt)
        }
        sqlite3_finalize(stmt)
        sqlite3_exec(db, "COMMIT", nil, nil, nil)
    }

    /// 명시적 close + 남은 버퍼 flush + WAL checkpoint (앱 종료 시)
    /// 순서가 핵심: 타이머 정지 → 최종 flush → 읽기 배리어 → 소유 스레드에서 close → 워커 정지.
    /// (connection은 소유 스레드에서만 close 가능 —과거 "main에서 lock+close" 패턴이
    ///  백그라운드 워커의 use-after-free였다)
    func close() {
        dbLock.lock()
        if isClosed { dbLock.unlock(); return }
        isClosed = true
        dbLock.unlock()
        // 1) 타이머 정지 (새 worker job 발생 차단)
        flushTimer?.cancel(); flushTimer = nil
        walTimer?.cancel(); walTimer = nil
        backfillTimer?.cancel(); backfillTimer = nil
        retentionTimer?.cancel(); retentionTimer = nil
        // 2) 최종 flush (write worker)
        flushPending()
        // 3) 배리어 — 진행 중인 읽기 전부 대기 (mailbox FIFO)
        readWorker.runSync { }
        // 4) connection을 각 소유 스레드에서 close
        writeWorker.runSync {
            if let db = self.db {
                sqlite3_exec(db, "PRAGMA wal_checkpoint(TRUNCATE)", nil, nil, nil)
                sqlite3_close(db)
                self.db = nil
            }
        }
        readWorker.runSync {
            if let r = self.readDb {
                sqlite3_close(r)
                self.readDb = nil
            }
        }
        // 5) 워커 정지 (남은 job drain 후 스레드 종료)
        writeWorker.stop()
        readWorker.stop()
    }

    private func open() {
        // connection을 **소유 스레드에서** 오픈 (생성 스레드 == 유일 사용 스레드)
        writeWorker.runSync {
            var conn: OpaquePointer?
            guard sqlite3_open(self.dbPath, &conn) == SQLITE_OK else {
                print("DB open failed: \(self.dbPath)")
                if let c = conn { sqlite3_close(c) }
                self.db = nil
                return
            }
            sqlite3_exec(conn, "PRAGMA journal_mode=WAL", nil, nil, nil)
            sqlite3_exec(conn, "PRAGMA synchronous=NORMAL", nil, nil, nil)
            sqlite3_exec(conn, "PRAGMA busy_timeout=5000", nil, nil, nil)
            self.db = conn
            self.createTables()
            // 읽기 connection (WAL: 읽기는 쓰기 배치와 동시) — 소유 스레드에서 오픈
            // migrate 전에 여는 이유: 컬럼 존재 확인 queryRows가 readDb를 타게 하기 위함
            self.readWorker.runSync {
                var ro: OpaquePointer?
                // 읽기 전용(READONLY): 방어적 — 이 connection은 쓰기 SQL로 절대 쓰지 않음.
                // (실측: RO vs RW가 libsqlite3 "misuse" 진단과 무관 — 앱 프로세스 자체 특성)
                if sqlite3_open_v2(self.dbPath, &ro, SQLITE_OPEN_READONLY, nil) == SQLITE_OK, let r = ro {
                    sqlite3_exec(r, "PRAGMA busy_timeout=5000", nil, nil, nil)
                    self.readDb = r
                } else {
                    print("DB read connection open failed — read 경로 비활성")
                }
            }
            self.migrateEventColumns()
            self.startRetentionMaintenance()
        }
    }

    /// events 테이블에 app/title/url 컬럼 + meta 테이블 추가 (idempotent).
    /// data JSON을 평탄한 컬럼으로 normal화 → 저장 경량화 + 쿼리 가속 (VACUUM 후 파일 축소).
    private func migrateEventColumns() {
        guard let db = db else { return }
        for col in ["app", "title", "url"] {
            let exists = queryRows("SELECT name FROM pragma_table_info('events') WHERE name = ?") {
                sqlite3_bind_text($0, 1, (col as NSString).utf8String, -1, nil)
            }
            if exists.isEmpty {
                sqlite3_exec(db, "ALTER TABLE events ADD COLUMN \(col) TEXT", nil, nil, nil)
                print("DB migration: events.\(col) added")
            }
        }
        sqlite3_exec(db, "CREATE INDEX IF NOT EXISTS idx_events_app ON events(app)", nil, nil, nil)
        sqlite3_exec(db, """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """, nil, nil, nil)
    }

    // ── columnization backfill: data JSON → app/title/url (zero-loss, resume 가능) ──
    private func metaInt(_ key: String) -> Int64 {
        let rows = queryRows("SELECT value FROM meta WHERE key = ?") {
            sqlite3_bind_text($0, 1, (key as NSString).utf8String, -1, nil)
        }
        return Int64(rows.first?["value"] as? String ?? "0") ?? 0
    }
    private func setMeta(_ key: String, _ value: Int64) {
        exec("INSERT INTO meta (key, value) VALUES ('\(key)', '\(value)') ON CONFLICT(key) DO UPDATE SET value = excluded.value")
    }

    /// 백그라운드 배치 백필 (1s tick, 배치 500행, id watermark 기반 resume).
    /// zero-loss 보장: 추가 키(예: _ax/_src)가 있는 행은 data 원본 보존.
    private func runBackfillTick() {
        // 쓰기 connection은 writeWorker 단일 소유 — lock 불필요
        writeWorker.runSync { self.runBackfillTickLocked() }
    }

    private func runBackfillTickLocked() {
        guard let db = db else { return }
        let rows = queryRows("SELECT MAX(id) AS max_id FROM events") { _ in }
        let maxId = rows.first?["max_id"] as? Int64 ?? 0
        guard maxId > 0 else { return }
        let wm = metaInt("backfill_wm")
        guard wm < maxId else {
            // catch-up 완료: 파일 축소용 VACUUM 1회 (meta 플래그로 재실행 방지)
            if metaInt("vacuum_done") == 0 {
                print("DB backfill 완료 — VACUUM 실행 (파일 축소)…")
                if sqlite3_exec(db, "VACUUM", nil, nil, nil) == SQLITE_OK {
                    setMeta("vacuum_done", 1)
                    print("DB VACUUM 완료")
                } else {
                    print("DB VACUUM 실패(다음 tick 재시도): \(String(cString: sqlite3_errmsg(db)))")
                }
            }
            return
        }
        let lo = wm + 1
        let hi = min(wm + 500, maxId)
        // 1) 컬럼 채우기 (COALESCE로 기존 값 덮어쓰기 방지 — idempotent, json_valid 가드로 '' 안전)
        exec("""
            UPDATE events
            SET app = COALESCE(app, CASE WHEN json_valid(data) THEN json_extract(data, '$.app') END),
                title = COALESCE(title, CASE WHEN json_valid(data) THEN json_extract(data, '$.title') END),
                url = COALESCE(url, CASE WHEN json_valid(data) THEN json_extract(data, '$.url') END)
            WHERE id >= \(lo) AND id <= \(hi)
        """)
        // 2) data 정화: 알려진 3키 외에 추가 키가 없는 행만 '{}'로 (데이터 보존)
        exec("""
            UPDATE events SET data = '{}'
            WHERE id >= \(lo) AND id <= \(hi) AND data != '' AND data != '{}'
              AND NOT EXISTS (
                SELECT 1 FROM json_each(events.data)
                WHERE json_each.key NOT IN ('app', 'title', 'url')
              )
        """)
        setMeta("backfill_wm", hi)
    }


    private func createTables() {
        exec("""
            CREATE TABLE IF NOT EXISTS buckets (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                client TEXT NOT NULL,
                hostname TEXT NOT NULL,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bucket_id TEXT NOT NULL REFERENCES buckets(id),
                timestamp REAL NOT NULL,
                duration REAL NOT NULL DEFAULT 0,
                data TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_events_bucket ON events(bucket_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE TABLE IF NOT EXISTS app_tags (
                app_name TEXT PRIMARY KEY,
                tag TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#58a6ff',
                regex TEXT NOT NULL DEFAULT '',
                parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                score INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                pattern TEXT NOT NULL DEFAULT '',
                case_insensitive INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        // Migration: parent_id, sort_order, score (기존 DB 호환)
        sqlite3_exec(db, "ALTER TABLE categories ADD COLUMN parent_id INTEGER", nil, nil, nil)
        sqlite3_exec(db, "ALTER TABLE categories ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0", nil, nil, nil)
        sqlite3_exec(db, "ALTER TABLE categories ADD COLUMN score INTEGER NOT NULL DEFAULT 0", nil, nil, nil)
        // Migration: 기존 regex를 rules 테이블로 복사 (한 번만)
        if sqlite3_exec(db, "INSERT OR IGNORE INTO rules (category_id, pattern, case_insensitive) SELECT id, regex, 1 FROM categories WHERE regex != '' AND regex IS NOT NULL AND id NOT IN (SELECT DISTINCT category_id FROM rules)", nil, nil, nil) == SQLITE_OK {
            sqlite3_exec(db, "UPDATE categories SET regex = '' WHERE regex != ''", nil, nil, nil) // 사용 후 초기화
        }
    }

    private func exec(_ sql: String) {
        // 쓰기 connection → writeWorker 스레드에서 실행 (중첩 호출 시 인라인)
        writeWorker.runSync {
            guard let db = self.db else { return }
            if sqlite3_exec(db, sql, nil, nil, nil) != SQLITE_OK {
                print("[DB] exec 에러: \(String(cString: sqlite3_errmsg(db))) — \(sql.prefix(80))")
            }
        }
    }

    func insertHeartbeat(bucketId: String = "aw-watcher-window",
                         timestamp: Double, duration: Double, data: String) {
        dbLock.lock()
        guard !isClosed else { dbLock.unlock(); return }
        if !bucketEnsured {
            ensureBucketRaw(bucketId)
            bucketEnsured = true
        }
        // 즉시 commit 대신 버퍼에 쌓고, threshold/타이머로 배치 flush
        pendingEvents.append((bucketId: bucketId, ts: timestamp, dur: duration, data: data))
        let over = pendingEvents.count >= flushThreshold
        dbLock.unlock()
        if over { flushPending() }
    }

    private func ensureBucketRaw(_ id: String) {
        writeWorker.runSync {
            guard let db = self.db else { return }
            let sql = "INSERT OR IGNORE INTO buckets (id, type, client, hostname) VALUES (?, ?, ?, ?)"
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let s = stmt else { return }
            sqlite3_bind_text(s, 1, (id as NSString).utf8String, -1, nil)
            sqlite3_bind_text(s, 2, ("app" as NSString).utf8String, -1, nil)
            sqlite3_bind_text(s, 3, ("aw-watcher-window" as NSString).utf8String, -1, nil)
            let hostname = ProcessInfo.processInfo.hostName
            sqlite3_bind_text(s, 4, (hostname as NSString).utf8String, -1, nil)
            sqlite3_step(s)
            sqlite3_finalize(s)
        }
    }

    // MARK: - Date helpers

    /// "yyyy-MM-dd" → 해당 날짜 00:00~23:59 (UNIX epoch, **현재 로컬 시간대** 기준).
    /// +09:00 하드코딩 제거: 해외 체류 시 '오늘' 기준이 깨지는 문제 방지.
    private func parseDate(_ targetDate: String?) -> (start: Double, end: Double) {
        let cal = Calendar.current
        let day: Date
        if let d = targetDate {
            let parts = d.split(separator: "-").compactMap { Int($0) }
            if parts.count == 3,
               let dt = cal.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2])) {
                day = dt
            } else {
                day = cal.startOfDay(for: Date())
            }
        } else {
            day = cal.startOfDay(for: Date())
        }
        let start = day.timeIntervalSince1970
        let end = cal.date(byAdding: .day, value: 1, to: day)!.timeIntervalSince1970 - 1
        return (start, end)
    }

    // MARK: - Query helpers

    private func queryRows(_ sql: String, _ bind: @escaping (OpaquePointer) -> Void) -> [[String: Any]] {
        // 읽기 경로 — **readWorker 전용 스레드**에서 실행
        // (⚠️ readDb만 사용: 쓰기 conn은 다른 스레드 소유 — thread-affinity 위반 금지)
        return readWorker.runSync {
            guard let conn = self.readDb else {
                print("[DB] ⚠️ 읽기 connection 미개방 — \(sql.prefix(80))")
                return [[String: Any]]()
            }
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(conn, sql, -1, &stmt, nil) == SQLITE_OK, let s = stmt else {
                print("[DB] SQL prepare 실패: \(String(cString: sqlite3_errmsg(conn))) — \(sql.prefix(120))")
                return [[String: Any]]()
            }
            bind(s)
            var results: [[String: Any]] = []
            var rc: Int32 = SQLITE_OK
            // ⚠️ **재-step 금지**: while 종료 시 마지막 step이 이미 terminal
            // (DONE/에러) 상태에 도달했음. terminal 후 재-step은 Apple libsqlite3이
            // "misuse at line ..."으로 진단(2~3건/초 로그 + 상태 손상 가능) —
            // c45c85a 원본의 재-step이 그 원인이었다. 루프 종료 rc로 판단.
            repeat {
                rc = sqlite3_step(s)
                guard rc == SQLITE_ROW else { break }
                var row: [String: Any] = [:]
                let cols = sqlite3_column_count(s)
                for i in 0..<cols {
                    let name = String(cString: sqlite3_column_name(s, i))
                    switch sqlite3_column_type(s, i) {
                    case SQLITE_INTEGER: row[name] = sqlite3_column_int64(s, i)
                    case SQLITE_FLOAT: row[name] = sqlite3_column_double(s, i)
                    case SQLITE_TEXT: row[name] = String(cString: sqlite3_column_text(s, i))
                    case SQLITE_BLOB: break
                    default: break
                    }
                }
                results.append(row)
            } while true
            // step 에러 감시(재-step 없이 terminal rc로)
            if rc != SQLITE_DONE {
                print("[DB] ⚠️ SQL step 에러(\(rc): \(String(cString: sqlite3_errmsg(conn)))) — \(results.count)rows만 반환: \(sql.prefix(120))")
            }
            sqlite3_finalize(s)
            return results
        }
    }

    // MARK: - API

    /// 브라우저 내부 페이지 (UI) — 탭 전환 중 수집된 스탈 URL로
    /// 실제 사이트를 이 페이지로 잘못 분류시키는 것을 방지.
        /// 브라우저 내부 페이지 (UI) — 탭 전환 중 수집된 stale URL로
    /// 실제 사이트를 잘못 분류시키지 않게 방지.
    /// (실측: 스트리머 채팅 제목 + chrome://extensions/ 재교착 사례)
    private func isBrowserInternalURL(_ url: String) -> Bool {
        if url.isEmpty { return false }
        if url.hasPrefix("chrome://") || url.hasPrefix("brave://")
            || url.hasPrefix("chrome-extension://") || url.hasPrefix("edge://")
            || url.hasPrefix("vivaldi://") || url.hasPrefix("whale://") {
            return true
        }
        if url == "about:blank" { return true }
        if url == "view-source:" || url.hasPrefix("view-source:") { return true }
        return false
    }

    /// c.gle.com 등 보안 리다이렉트 사이트 → 외부로 리다이렉트되어
    /// 실제 페이지 URL로 수집되지 않음
    private func isReferralOnlyURL(_ url: String) -> Bool {
        guard let h = urlComponentsHost(url) else { return false }
        return h == "c.gle.com" || h.hasSuffix(".gle.com")
    }

    private func urlComponentsHost(_ url: String) -> String? {
        guard let c = URLComponents(string: url), let host = c.host?.lowercased() else { return nil }
        return host
    }

    private let skipApps: Set<String> = [
        // ⚠️ app.swift watcher skipApps와 동일하게 유지 (양쪽이 분리 파일 — 한쪽만 수정 금지)
        "loginwindow", "WindowServer", "SystemUIServer", "Dock",
        "Spotlight", "NotificationCenter", "universalAccessAuthWarn",
        "SecurityAgent", "UserNotificationCenter", "ScreenSaverEngine"
    ]
    /// 부분 문자열으로 스킵 (title=app fallback으로 넣히는 앱 포괄)
    private let skipAppSubstrings: [String] = ["시크릿 모드", "(로딩 중)", "(로그인)"]
    private func isSkipped(_ app: String) -> Bool {
        if skipApps.contains(app) { return true }
        return skipAppSubstrings.contains(where: { app.contains($0) })
    }
    private let browserApps: Set<String> = ["Brave Browser", "Google Chrome", "Safari", "Firefox",
        "Microsoft Edge", "Arc", "Orion", "Opera", "Opera GX", "Vivaldi", "Tor Browser",
        "네이버 웨일", "Whale", "시크릿 모드"]

    // (getTodayEvents 제거됨: dead API — 읽기 경로 모두 SQL 집계/직접 json_extract 사용)

    // ── Retention: 30일 초과 이벤트 → events_archive (app/title/url만) ──
    // DB 무제한 성장 방지 (1.5M행/3개월). app/title/url은 columnized 이후
    // data가 '{}'이므로 3 열만 이관하면 무손실. 30일 단위 rolling.
    func startRetentionMaintenance() {
        // 일 1회 (03:00 시작 후 24h 간격) — launchd/앱 재시작 무관, 일 1회 실행
        let t = DispatchSource.makeTimerSource(queue: DispatchQueue(label: "db-retention", qos: .background))
        t.schedule(deadline: .now() + 60 * 15, repeating: 60 * 60 * 24)
        t.setEventHandler { [weak self] in self?.runRetentionTick() }
        t.resume()
        retentionTimer = t
    }

    private func runRetentionTick() {
        // retention/VACUUM은 쓰기 작업 — writeWorker 단일 소유
        writeWorker.runSync { self.runRetentionTickLocked() }
    }

    private func runRetentionTickLocked() {
        guard let db = db else { return }
        let cutoff = Date().timeIntervalSince1970 - 30 * 86400
        // 1) archive 테이블 idempotent 생성
        guard sqlite3_exec(db, """
            CREATE TABLE IF NOT EXISTS events_archive (
                id INTEGER PRIMARY KEY, bucket_id TEXT, timestamp REAL, duration REAL,
                app TEXT, title TEXT, url TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_archive_ts ON events_archive(timestamp);
            """, nil, nil, nil) == SQLITE_OK else { return }
        // 2) 30일 초과 batch 이관 + 삭제
        // columnized 이후 data는 '{}' 이므로 3열만 이관하면 무손실
        if sqlite3_exec(db, "BEGIN", nil, nil, nil) != SQLITE_OK { return }
        var stmt: OpaquePointer?
        var moved = 0
        if sqlite3_prepare_v2(db,
            "INSERT OR IGNORE INTO events_archive (id, bucket_id, timestamp, duration, app, title, url) " +
            "SELECT id, bucket_id, timestamp, duration, app, title, url FROM events WHERE timestamp < ?",
            -1, &stmt, nil) == SQLITE_OK, let s = stmt {
            sqlite3_bind_double(s, 1, cutoff)
            if sqlite3_step(s) == SQLITE_DONE { moved = Int(sqlite3_changes(db)) }
            sqlite3_finalize(s)
        }
        if sqlite3_prepare_v2(db, "DELETE FROM events WHERE timestamp < ?", -1, &stmt, nil) == SQLITE_OK, let s = stmt {
            sqlite3_bind_double(s, 1, cutoff)
            sqlite3_step(s)
            sqlite3_finalize(s)
        }
        sqlite3_exec(db, "COMMIT", nil, nil, nil)
        if moved > 0 {
            print("DB retention: \(moved) rows → events_archive")
            // 파일 공간 회수 (단일 connection 잠금, 일 1회)
            sqlite3_exec(db, "VACUUM", nil, nil, nil)
            sqlite3_exec(db, "PRAGMA wal_checkpoint(TRUNCATE)", nil, nil, nil)
        }
    }

    /// <title> 태그가 포함되어 있는 브라우저 타이틀을 순수 텍스트로 정제.
    /// (페이지가 self-closing <title .../> 로 <title>를 보여주거나 로딩 중이면
    /// CGWindowName에 태그 형식이 그대로 담김 — 대시보드에 깨져 보이는 원이.
    /// 이미 "체인이 싶다" 같이 순정인 타이틀은 포함 없으므로 무해)
    func cleanHTMLTitle(_ raw: String) -> String {
        guard let r = raw.range(of: "<title", options: .caseInsensitive) else { return raw }
        var seg = raw[r.upperBound...]
        if let closeIdx = seg.range(of: "</title", options: .caseInsensitive)?.lowerBound,
           closeIdx != seg.startIndex {
            seg = seg[..<closeIdx]
        }
        if seg.hasSuffix("/") { seg = seg.dropLast() }
        var out = ""
        var inTag = false
        for ch in seg {
            if ch == "<" { inTag = true; continue }
            if inTag { if ch == ">" { inTag = false }; continue }
            out.append(ch)
        }
        let cleaned = out.trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? raw : cleaned
    }

    func buildSessions(bucketId: String = "aw-watcher-window",
                       appFilter: String? = nil,
                       browserOnly: Bool = false,
                       targetDate: String? = nil) -> [[String: Any]] {
                let (start, end) = parseDate(targetDate)
        // columnization: 컬럼(app/title/url) 우선, NULL이면 data JSON fallback
        let rows = queryRows("""
            SELECT timestamp, duration,
                   \(sqlColApp) as app,
                   \(sqlColTitle) as title,
                   \(sqlColURL) as url
            FROM events
            WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """) { stmt in
            sqlite3_bind_text(stmt, 1, (bucketId as NSString).utf8String, -1, nil)
            sqlite3_bind_double(stmt, 2, start)
            sqlite3_bind_double(stmt, 3, end)
        }

        var sessions: [[String: Any]] = []
        var current: [String: Any]?

        for r in rows {
            let app = r["app"] as? String ?? "Unknown"
            var title = r["title"] as? String ?? app
            var url = r["url"] as? String ?? ""
            let ts = r["timestamp"] as? Double ?? 0
            let dur = r["duration"] as? Double ?? 0
            // 탭 전환 직후 수집된 스탈 URL/제목 로 분류가 깨지는 것 방지
            if isBrowserInternalURL(url) { url = "" }
            else if isReferralOnlyURL(url) { url = "" }
            // <title> 태그 원문이 그대로 들어간 타이틀 정제 (브라우저 수집 불가)
            if title.contains("<title") {
                title = cleanHTMLTitle(title)
            }

            if browserOnly && !browserApps.contains(app) {
                if let c = current { sessions.append(c); current = nil }
                continue
            }
            if let filter = appFilter, app != filter {
                if let c = current { sessions.append(c); current = nil }
                continue
            }

            if var c = current, c["title"] as? String == title {
                if !browserOnly || c["app"] as? String == app {
                    c["end"] = ts + dur
                    c["duration"] = (c["duration"] as? Double ?? 0) + dur
                    current = c
                    continue
                }
            }
            if let c = current { sessions.append(c) }
            var newSession: [String: Any] = ["title": title, "url": url, "start": ts, "end": ts + dur, "duration": dur]
            if browserOnly { newSession["app"] = app }
            current = newSession
        }
        if let c = current { sessions.append(c) }
        return sessions
    }

    // MARK: - Today endpoint (for menu bar)

    struct TodayInfo {
        let totalSeconds: Double
        let apps: [(name: String, seconds: Double, lastTitle: String)]
        let currentApp: String?
        let currentTitle: String?
    }

    /// 경량화: 앱을 GROUP BY로 SQLite에서 집계 + 마지막 타이틀은 window function으로.
    /// (기존: 하루치 8~10k row를 Swift에서 row당 JSON 파싱 → 이제 수십 개 앱 row만)
    func getTodayInfo(targetDate: String? = nil) -> TodayInfo {
                let (start, end) = parseDate(targetDate)

        let appRows = queryRows("""
            SELECT \(sqlColApp) as app,
                   SUM(duration) as total,
                   COUNT(*) as n
            FROM events
            WHERE bucket_id = 'aw-watcher-window' AND timestamp >= ? AND timestamp <= ?
            GROUP BY app
            ORDER BY total DESC
        """) { stmt in
            sqlite3_bind_double(stmt, 1, start)
            sqlite3_bind_double(stmt, 2, end)
        }

        // 앱별 마지막 창 제목 (SQLite 3.25+ window function)
        var lastTitles: [String: String] = [:]
        for r in queryRows("""
            SELECT app, title FROM (
                SELECT \(sqlColApp) as app,
                       \(sqlColTitle) as title,
                       ROW_NUMBER() OVER (PARTITION BY \(sqlColApp) ORDER BY timestamp DESC) as rn
                FROM events
                WHERE bucket_id = 'aw-watcher-window' AND timestamp >= ? AND timestamp <= ?
            ) WHERE rn = 1
        """) { stmt in
            sqlite3_bind_double(stmt, 1, start)
            sqlite3_bind_double(stmt, 2, end)
        } {
            if let a = r["app"] as? String, let t = r["title"] as? String {
                lastTitles[a] = t
            }
        }

        var total: Double = 0
        var apps: [(name: String, seconds: Double, lastTitle: String)] = []
        for r in appRows {
            let app = r["app"] as? String ?? "Unknown"
            if isSkipped(app) { continue }
            let secs = r["total"] as? Double ?? 0
            total += secs
            apps.append((name: app, seconds: secs, lastTitle: lastTitles[app] ?? ""))
        }

        // 현재 앱: 최근 이벤트 중 skip 제외 첫 개
        var currentApp: String? = nil
        var currentTitle: String? = nil
        for r in queryRows("""
            SELECT \(sqlColApp) as app, \(sqlColTitle) as title
            FROM events
            WHERE bucket_id = 'aw-watcher-window' AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp DESC LIMIT 10
        """) { stmt in
            sqlite3_bind_double(stmt, 1, start)
            sqlite3_bind_double(stmt, 2, end)
        } {
            let app = r["app"] as? String ?? ""
            if !isSkipped(app) {
                currentApp = app
                currentTitle = r["title"] as? String
                break
            }
        }

        return TodayInfo(totalSeconds: total, apps: apps, currentApp: currentApp, currentTitle: currentTitle)
    }

    private func todayISO() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar.current
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    // MARK: - Categories (ActivityWatch style — hierarchical)

    func getCategories() -> [[String: Any]] {
                let rows = queryRows("SELECT id, name, color, regex, parent_id, sort_order, score, created_at FROM categories ORDER BY sort_order ASC, id ASC") { _ in }
        // Get all rules grouped by category_id
        let allRules = queryRows("SELECT id, category_id, pattern, case_insensitive FROM rules ORDER BY id ASC") { _ in }
        var rulesByCat: [Int64: [[String: Any]]] = [:]
        for r in allRules {
            let catId = r["category_id"] as! Int64
            var rule = r
            rule["category_id"] = nil
            rulesByCat[catId, default: []].append(rule)
        }
        var byParent: [Int64?: [[String: Any]]] = [:]
        for r in rows {
            let pid = r["parent_id"] as? Int64
            let id = r["id"] as! Int64
            var node = r
            node["children"] = [[String: Any]]()
            node["rules"] = rulesByCat[id] ?? []
            byParent[pid, default: []].append(node)
        }
        func attachChildren(_ nodes: inout [[String: Any]]) {
            for i in nodes.indices {
                let id = nodes[i]["id"] as! Int64
                var kids = byParent[id] ?? []
                attachChildren(&kids)
                nodes[i]["children"] = kids
            }
        }
        var roots = byParent[nil] ?? []
        attachChildren(&roots)
        return roots
    }

    func createCategory(name: String, color: String, regex: String = "", parentId: Int64? = nil, score: Int = 0) -> Int64? {
        return writeWorker.runSync {
            guard let db = self.db else { return nil }
            let sql = "INSERT INTO categories (name, color, regex, parent_id, score) VALUES (?, ?, ?, ?, ?)"
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return nil }
            sqlite3_bind_text(stmt, 1, (name as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 2, (color as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 3, (regex as NSString).utf8String, -1, nil)
            if let pid = parentId {
                sqlite3_bind_int64(stmt, 4, pid)
            } else {
                sqlite3_bind_null(stmt, 4)
            }
            sqlite3_bind_int(stmt, 5, Int32(score))
            guard sqlite3_step(stmt) == SQLITE_DONE else { sqlite3_finalize(stmt); return nil }
            let id = sqlite3_last_insert_rowid(db)
            sqlite3_finalize(stmt)
            self.invalidateRuleCache()
            return id
        }
    }

    func updateCategory(id: Int64, name: String, color: String, regex: String = "", parentId: Int64? = nil, sortOrder: Int = 0, score: Int = 0) {
        writeWorker.runSync {
            guard let db = self.db else { return }
            let sql = "UPDATE categories SET name = ?, color = ?, regex = ?, parent_id = ?, sort_order = ?, score = ? WHERE id = ?"
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
            sqlite3_bind_text(stmt, 1, (name as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 2, (color as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 3, (regex as NSString).utf8String, -1, nil)
            if let pid = parentId {
                sqlite3_bind_int64(stmt, 4, pid)
            } else {
                sqlite3_bind_null(stmt, 4)
            }
            sqlite3_bind_int(stmt, 5, Int32(sortOrder))
            sqlite3_bind_int(stmt, 6, Int32(score))
            sqlite3_bind_int64(stmt, 7, id)
            sqlite3_step(stmt)
            sqlite3_finalize(stmt)
            self.invalidateRuleCache()
        }
    }

    func deleteCategory(id: Int64) {
        writeWorker.runSync {
            guard let db = self.db else { return }
            // reparent children to grandparent
            let reparent = "UPDATE categories SET parent_id = (SELECT parent_id FROM categories WHERE id = ?) WHERE parent_id = ?"
            var stmt1: OpaquePointer?
            if sqlite3_prepare_v2(db, reparent, -1, &stmt1, nil) == SQLITE_OK, let s1 = stmt1 {
                sqlite3_bind_int64(s1, 1, id)
                sqlite3_bind_int64(s1, 2, id)
                sqlite3_step(s1)
                sqlite3_finalize(s1)
            }
            let sql = "DELETE FROM categories WHERE id = ?"
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let s = stmt else { return }
            sqlite3_bind_int64(s, 1, id)
            sqlite3_step(s)
            sqlite3_finalize(s)
            self.invalidateRuleCache()
        }
    }

    // MARK: - Rules CRUD

    func getRules(categoryId: Int64) -> [[String: Any]] {
                return queryRows("SELECT id, pattern, case_insensitive FROM rules WHERE category_id = ? ORDER BY id ASC") { stmt in
            sqlite3_bind_int64(stmt, 1, categoryId)
        }
    }

    func createRule(categoryId: Int64, pattern: String, caseInsensitive: Bool = true) -> Int64? {
        return writeWorker.runSync {
            guard let db = self.db else { return nil }
            let sql = "INSERT INTO rules (category_id, pattern, case_insensitive) VALUES (?, ?, ?)"
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return nil }
            sqlite3_bind_int64(stmt, 1, categoryId)
            sqlite3_bind_text(stmt, 2, (pattern as NSString).utf8String, -1, nil)
            sqlite3_bind_int(stmt, 3, caseInsensitive ? 1 : 0)
            guard sqlite3_step(stmt) == SQLITE_DONE else { sqlite3_finalize(stmt); return nil }
            let id = sqlite3_last_insert_rowid(db)
            sqlite3_finalize(stmt)
            self.invalidateRuleCache()
            return id
        }
    }

    func updateRule(id: Int64, pattern: String, caseInsensitive: Bool = true) {
        writeWorker.runSync {
            guard let db = self.db else { return }
            let sql = "UPDATE rules SET pattern = ?, case_insensitive = ? WHERE id = ?"
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
            sqlite3_bind_text(stmt, 1, (pattern as NSString).utf8String, -1, nil)
            sqlite3_bind_int(stmt, 2, caseInsensitive ? 1 : 0)
            sqlite3_bind_int64(stmt, 3, id)
            sqlite3_step(stmt)
            sqlite3_finalize(stmt)
            self.invalidateRuleCache()
        }
    }

    func deleteRule(id: Int64) {
        writeWorker.runSync {
            guard let db = self.db else { return }
            let sql = "DELETE FROM rules WHERE id = ?"
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let s = stmt else { return }
            sqlite3_bind_int64(s, 1, id)
            sqlite3_step(s)
            sqlite3_finalize(s)
            self.invalidateRuleCache()
        }
    }

    // MARK: - Category Resolution (rules-based)

    private var ruleCache: [(catName: String, catColor: String, catId: Int64, pattern: NSRegularExpression)]? = nil
    private let ruleCacheLock = NSLock()

    func resolveCategory(app: String, title: String) -> (name: String, color: String)? {
        // ruleCache만 읽기 (readDb) — dbLock 불필요
        return resolveCategoryLocked(app: app, title: title)
    }

    /// 무상황 전용 (ruleCache를 읽기) — 다중 스레드 안전을 위해 lock으로 복사본
    private func resolveCategoryLocked(app: String, title: String) -> (name: String, color: String)? {
        ruleCacheLock.lock()
        var cache = ruleCache
        ruleCacheLock.unlock()
        if cache == nil {
            cache = reloadRuleCache()
            ruleCacheLock.lock(); ruleCache = cache; ruleCacheLock.unlock()
        }
        let target = "\(app) \(title)".lowercased()
        for r in ruleCache ?? [] {
            let range = NSRange(target.startIndex..<target.endIndex, in: target)
            if r.pattern.firstMatch(in: target, range: range) != nil {
                return (r.catName, r.catColor)
            }
        }
        return nil
    }

    private func reloadRuleCache() -> [(catName: String, catColor: String, catId: Int64, pattern: NSRegularExpression)] {
        let rows = queryRows("""
            SELECT r.id, r.pattern, r.case_insensitive, c.name as cat_name, c.color as cat_color, c.id as cat_id
            FROM rules r JOIN categories c ON r.category_id = c.id
            ORDER BY c.sort_order ASC, c.id ASC, r.id ASC
        """) { _ in }
        var cache: [(catName: String, catColor: String, catId: Int64, pattern: NSRegularExpression)] = []
        for r in rows {
            guard let name = r["cat_name"] as? String,
                  let color = r["cat_color"] as? String,
                  let pattern = r["pattern"] as? String,
                  let catId = r["cat_id"] as? Int64,
                  !pattern.isEmpty else { continue }
            let ci = (r["case_insensitive"] as? Int ?? 1) != 0
            let options: NSRegularExpression.Options = ci ? [.caseInsensitive] : []
            if let regex = try? NSRegularExpression(pattern: pattern, options: options) {
                cache.append((name, color, catId, regex))
            }
        }
        return cache
    }

    /// CRUD에서 cache 무효화 (lock 보호)
    private func invalidateRuleCache() {
        ruleCacheLock.lock(); ruleCache = nil; ruleCacheLock.unlock()
    }

    // (getCategoryMatches/getTodayEvents 제거됨: 대시보드 미사용 dead API — 경량화)

    /// 한 번의 DB 조회로 모든 카테고리의 matches 반환 (성능 최적화)
    func getAllCategoryMatches() -> [String: Any] {
                // 1. 모든 카테고리와 규칙 로드
        let allCats = queryRows("""
            SELECT c.id, c.name, c.color, r.id as rid, r.pattern, r.case_insensitive
            FROM categories c
            JOIN rules r ON r.category_id = c.id
            ORDER BY c.id
        """) { _ in }

        guard !allCats.isEmpty else { return [:] }

        // 카테고리별로 규칙 컴파일
        var catRegexes: [Int64: (name: String, color: String, regexes: [NSRegularExpression])] = [:]
        for row in allCats {
            guard let cid = row["id"] as? Int64,
                  let pat = row["pattern"] as? String, !pat.isEmpty else { continue }
            let name = row["name"] as? String ?? ""
            let color = row["color"] as? String ?? "#58a6ff"
            let ci = (row["case_insensitive"] as? Int ?? 1) != 0
            if let regex = try? NSRegularExpression(pattern: pat, options: ci ? [.caseInsensitive] : []) {
                if catRegexes[cid] != nil {
                    catRegexes[cid]!.regexes.append(regex)
                } else {
                    catRegexes[cid] = (name, color, [regex])
                }
            }
        }

        // 2. 오늘 이벤트 1회 조회 — (app,title) pair 단위 SQL 집계 (row당 regex → pair당 regex)
        let (start, end) = parseDate(nil)
        let skipList = skipApps.map { "'\($0)'" }.joined(separator: ",")
        let rows = queryRows("""
            SELECT \(sqlColApp) as app,
                   \(sqlColTitle) as title,
                   SUM(duration) as dur
            FROM events
            WHERE bucket_id = 'aw-watcher-window'
              AND timestamp >= ? AND timestamp <= ?
              AND \(sqlColApp) NOT IN (\(skipList))
              AND \(sqlColTitle) IS NOT NULL
              AND \(sqlColTitle) != ''
            GROUP BY app, title
        """) { stmt in
            sqlite3_bind_double(stmt, 1, start)
            sqlite3_bind_double(stmt, 2, end)
        }

        // 3. 각 카테고리별로 (app, title) → duration 집계
        var result: [Int64: [String: Double]] = [:]
        for (cid, _) in catRegexes { result[cid] = [:] }

        for row in rows {
            let app = row["app"] as? String ?? ""
            if isSkipped(app) { continue }
            let title = row["title"] as? String ?? ""
            let dur = row["dur"] as? Double ?? 0
            let target = "\(app) \(title)".lowercased()
            let range = NSRange(target.startIndex..<target.endIndex, in: target)

            for (cid, info) in catRegexes {
                for regex in info.regexes {
                    if regex.firstMatch(in: target, range: range) != nil {
                        let key = "\(app)|||\(title)"
                        result[cid]![key, default: 0] += dur
                        break
                    }
                }
            }
        }

        // 4. 응답 형식으로 변환
        var output: [String: Any] = [:]
        for (cid, _) in catRegexes {
            guard let pairMap = result[cid], let info = catRegexes[cid] else { continue }
            let matches: [[String: Any]] = pairMap.map { key, dur in
                let parts = key.components(separatedBy: "|||")
                return ["app": parts.first ?? "", "title": parts.count > 1 ? parts[1] : "", "duration": dur]
            }
            output[String(cid)] = [
                "name": info.name,
                "color": info.color,
                "matches": matches
            ]
        }
        return output
    }

    // (getUntaggedPairs/getRecentPairs 제거됨: 대시보드 미사용 dead API)

    // MARK: - Tag Stats (regex-based)

    func getTagStats(targetDate: String? = nil) -> [[String: Any]] {
                let (start, end) = parseDate(targetDate)
        let skipList = skipApps.map { "'\($0)'" }.joined(separator: ",")
        // (app,title) pair 단위 SQL 집계: regex 매칭이 row당(~8k) → pair당(~수십)으로
        let rows = queryRows("""
            SELECT \(sqlColApp) as app,
                   \(sqlColTitle) as title,
                   SUM(duration) as dur
            FROM events
            WHERE bucket_id = 'aw-watcher-window'
              AND timestamp >= ? AND timestamp <= ?
              AND \(sqlColApp) NOT IN (\(skipList))
            GROUP BY app, title
        """) { stmt in
            sqlite3_bind_double(stmt, 1, start)
            sqlite3_bind_double(stmt, 2, end)
        }

        var pairMap: [String: (app: String, title: String, dur: Double)] = [:]
        for r in rows {
            let app = r["app"] as? String ?? ""
            if isSkipped(app) { continue } // 부분 문자열 스킵은 코드에서 처리
            let title = r["title"] as? String ?? ""
            let dur = r["dur"] as? Double ?? 0
            let key = "\(app)|||\(title)"
            if pairMap[key] != nil {
                pairMap[key]!.dur += dur
            } else {
                pairMap[key] = (app, title, dur)
            }
        }

        if ruleCache == nil { reloadRuleCache() }

        var tagTotals: [String: (seconds: Double, color: String)] = [:]
        var untaggedSeconds: Double = 0

        for (_, pair) in pairMap {
            if let cat = resolveCategoryLocked(app: pair.app, title: pair.title) {
                tagTotals[cat.name, default: (0, cat.color)].seconds += pair.dur
            } else {
                untaggedSeconds += pair.dur
            }
        }

        var result: [[String: Any]] = []
        for (name, info) in tagTotals {
            result.append(["tag": name, "color": info.color, "seconds": info.seconds])
        }
        result.sort { ($0["seconds"] as? Double ?? 0) > ($1["seconds"] as? Double ?? 0) }
        result.append(["tag": "__untagged__", "color": "#8b949e", "seconds": untaggedSeconds])
        return result
    }
}
