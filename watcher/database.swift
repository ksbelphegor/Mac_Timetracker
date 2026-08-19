import Foundation
import SQLite3

// MARK: - Database

class Database {
    static let shared = Database()
    var db: OpaquePointer?
    let dbPath: String
    /// 단일 connection SQLite는 thread-safe가 아님 — 모든 접근에 lock
    private let dbLock = NSLock()

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

    /// 명시적 close + WAL checkpoint (앱 종료 시 권장)
    func close() {
        dbLock.lock()
        defer { dbLock.unlock() }
        guard let db = db else { return }
        sqlite3_exec(db, "PRAGMA wal_checkpoint(TRUNCATE)", nil, nil, nil)
        sqlite3_close(db)
        self.db = nil
    }

    private func open() {
        dbLock.lock()
        defer { dbLock.unlock() }
        guard sqlite3_open(dbPath, &db) == SQLITE_OK else {
            print("DB open failed: \(dbPath)")
            db = nil
            return
        }
        sqlite3_exec(db, "PRAGMA journal_mode=WAL", nil, nil, nil)
        sqlite3_exec(db, "PRAGMA synchronous=NORMAL", nil, nil, nil)
        createTables()
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
        sqlite3_exec(db, sql, nil, nil, nil)
    }

    func ensureBucket(_ id: String = "aw-watcher-window",
                      type: String = "app",
                      client: String = "aw-watcher-window") {
        let sql = "INSERT OR IGNORE INTO buckets (id, type, client, hostname) VALUES (?, ?, ?, ?)"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
        sqlite3_bind_text(stmt, 1, (id as NSString).utf8String, -1, nil)
        sqlite3_bind_text(stmt, 2, (type as NSString).utf8String, -1, nil)
        sqlite3_bind_text(stmt, 3, (client as NSString).utf8String, -1, nil)
        let hostname = ProcessInfo.processInfo.hostName
        sqlite3_bind_text(stmt, 4, (hostname as NSString).utf8String, -1, nil)
        sqlite3_step(stmt)
        sqlite3_finalize(stmt)
    }

    func insertHeartbeat(bucketId: String = "aw-watcher-window",
                         timestamp: Double, duration: Double, data: String) {
        ensureBucket(bucketId)
        let sql = "INSERT INTO events (bucket_id, timestamp, duration, data) VALUES (?, ?, ?, ?)"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
        sqlite3_bind_text(stmt, 1, (bucketId as NSString).utf8String, -1, nil)
        sqlite3_bind_double(stmt, 2, timestamp)
        sqlite3_bind_double(stmt, 3, duration)
        sqlite3_bind_text(stmt, 4, (data as NSString).utf8String, -1, nil)
        sqlite3_step(stmt)
        sqlite3_finalize(stmt)
    }

    // MARK: - Date helpers

    private func parseDate(_ targetDate: String?) -> (start: Double, end: Double) {
        let cal = Calendar.current
        let now = Date()
        let day: Date
        if let d = targetDate, let parsed = ISO8601DateFormatter().date(from: d + "T00:00:00+09:00") {
            day = parsed
        } else {
            day = cal.startOfDay(for: now)
        }
        let start = day.timeIntervalSince1970
        let end = cal.date(byAdding: .day, value: 1, to: day)!.timeIntervalSince1970 - 1
        return (start, end)
    }

    // MARK: - Query helpers

    private func queryRows(_ sql: String, _ bind: (OpaquePointer) -> Void) -> [[String: Any]] {
        var stmt: OpaquePointer?
        var results: [[String: Any]] = []
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }
        bind(stmt!)
        while sqlite3_step(stmt) == SQLITE_ROW {
            var row: [String: Any] = [:]
            let cols = sqlite3_column_count(stmt)
            for i in 0..<cols {
                let name = String(cString: sqlite3_column_name(stmt, i))
                switch sqlite3_column_type(stmt, i) {
                case SQLITE_INTEGER: row[name] = sqlite3_column_int64(stmt, i)
                case SQLITE_FLOAT: row[name] = sqlite3_column_double(stmt, i)
                case SQLITE_TEXT: row[name] = String(cString: sqlite3_column_text(stmt, i))
                case SQLITE_BLOB: break
                default: break
                }
            }
            results.append(row)
        }
        sqlite3_finalize(stmt)
        return results
    }

    // MARK: - API

    private let skipApps: Set<String> = [
        "loginwindow", "WindowServer", "SystemUIServer", "Dock", "Spotlight", "NotificationCenter"
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

    func getTodayEvents(bucketId: String = "aw-watcher-window",
                        targetDate: String? = nil) -> [[String: Any]] {
        let (start, end) = parseDate(targetDate)
        return queryRows("""
            SELECT timestamp, duration, data FROM events
            WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """) { stmt in
            sqlite3_bind_text(stmt, 1, (bucketId as NSString).utf8String, -1, nil)
            sqlite3_bind_double(stmt, 2, start)
            sqlite3_bind_double(stmt, 3, end)
        }
    }

    func getAppSummary(bucketId: String = "aw-watcher-window",
                       startDate: String? = nil, endDate: String? = nil) -> [[String: Any]] {
        let start = startDate ?? todayISO()
        let end = endDate ?? todayISO()
        let (s, e) = (parseDate(start).start, parseDate(end).end)
        return queryRows("""
            SELECT date(timestamp, 'unixepoch') as day,
                   json_extract(data, '$.app') as app,
                   SUM(duration) as total_seconds
            FROM events
            WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
            GROUP BY day, app
            ORDER BY day DESC, total_seconds DESC
        """) { stmt in
            sqlite3_bind_text(stmt, 1, (bucketId as NSString).utf8String, -1, nil)
            sqlite3_bind_double(stmt, 2, s)
            sqlite3_bind_double(stmt, 3, e)
        }
    }

    func getHourlyBreakdown(bucketId: String = "aw-watcher-window",
                            targetDate: String? = nil) -> [String: [String: Double]] {
        let (start, end) = parseDate(targetDate)
        let rows = queryRows("""
            SELECT timestamp, duration, data FROM events
            WHERE bucket_id = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """) { stmt in
            sqlite3_bind_text(stmt, 1, (bucketId as NSString).utf8String, -1, nil)
            sqlite3_bind_double(stmt, 2, start)
            sqlite3_bind_double(stmt, 3, end)
        }

        var hourly: [String: [String: Double]] = [:]
        for r in rows {
            guard let dataStr = r["data"] as? String,
                  let data = try? JSONSerialization.jsonObject(with: dataStr.data(using: .utf8)!) as? [String: String],
                  let app = data["app"] else { continue }
            let ts = r["timestamp"] as? Double ?? 0
            let dur = r["duration"] as? Double ?? 0
            // local timezone 시간대 (기존 버저: UTC 기반 → 한국 시간대 1~8시가 00:00에 모두 몰림)
            let cal = Calendar.current
            let hour = cal.component(.hour, from: Date(timeIntervalSince1970: ts))
            let hourStr = String(format: "%02d:00", hour)
            hourly[hourStr, default: [:]][app, default: 0] += dur
        }
        return hourly
    }

    func buildSessions(bucketId: String = "aw-watcher-window",
                       appFilter: String? = nil,
                       browserOnly: Bool = false,
                       targetDate: String? = nil) -> [[String: Any]] {
        let (start, end) = parseDate(targetDate)
        let rows = queryRows("""
            SELECT timestamp, duration, data FROM events
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
            guard let dataStr = r["data"] as? String,
                  let data = try? JSONSerialization.jsonObject(with: dataStr.data(using: .utf8)!) as? [String: String] else { continue }
            let app = data["app"] ?? "Unknown"
            let title = data["title"] ?? app
            let url = data["url"] ?? ""
            let ts = r["timestamp"] as? Double ?? 0
            let dur = r["duration"] as? Double ?? 0

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

    func getTodayInfo(targetDate: String? = nil) -> TodayInfo {
        let events = getTodayEvents(targetDate: targetDate)
        var appDict: [String: Double] = [:]
        var appTitles: [String: String] = [:]
        var total: Double = 0

        for e in events {
            guard let dataStr = e["data"] as? String,
                  let data = try? JSONSerialization.jsonObject(with: dataStr.data(using: .utf8)!) as? [String: String] else { continue }
            let app = data["app"] ?? "Unknown"
            if isSkipped(app) { continue }
            let title = data["title"] ?? ""
            let dur = e["duration"] as? Double ?? 0
            appDict[app, default: 0] += dur
            appTitles[app] = title
            total += dur
        }

        let sortedApps = appDict.sorted { $0.value > $1.value }
            .map { (name: $0.key, seconds: $0.value, lastTitle: appTitles[$0.key] ?? "") }

        var currentApp: String? = nil
        var currentTitle: String? = nil
        for e in events.reversed() {
            guard let dataStr = e["data"] as? String,
                  let data = try? JSONSerialization.jsonObject(with: dataStr.data(using: .utf8)!) as? [String: String] else { continue }
            let app = data["app"] ?? ""
            if !isSkipped(app) {
                currentApp = app
                currentTitle = data["title"]
                break
            }
        }

        return TodayInfo(totalSeconds: total, apps: sortedApps, currentApp: currentApp, currentTitle: currentTitle)
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
        ruleCache = nil
        return id
    }

    func updateCategory(id: Int64, name: String, color: String, regex: String = "", parentId: Int64? = nil, sortOrder: Int = 0, score: Int = 0) {
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
        ruleCache = nil
    }

    func deleteCategory(id: Int64) {
        // reparent children to grandparent
        let reparent = "UPDATE categories SET parent_id = (SELECT parent_id FROM categories WHERE id = ?) WHERE parent_id = ?"
        var stmt1: OpaquePointer?
        if sqlite3_prepare_v2(db, reparent, -1, &stmt1, nil) == SQLITE_OK {
            sqlite3_bind_int64(stmt1, 1, id)
            sqlite3_bind_int64(stmt1, 2, id)
            sqlite3_step(stmt1)
            sqlite3_finalize(stmt1)
        }
        let sql = "DELETE FROM categories WHERE id = ?"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
        sqlite3_bind_int64(stmt, 1, id)
        sqlite3_step(stmt)
        sqlite3_finalize(stmt)
        ruleCache = nil
    }

    // MARK: - Rules CRUD

    func getRules(categoryId: Int64) -> [[String: Any]] {
        return queryRows("SELECT id, pattern, case_insensitive FROM rules WHERE category_id = ? ORDER BY id ASC") { stmt in
            sqlite3_bind_int64(stmt, 1, categoryId)
        }
    }

    func createRule(categoryId: Int64, pattern: String, caseInsensitive: Bool = true) -> Int64? {
        let sql = "INSERT INTO rules (category_id, pattern, case_insensitive) VALUES (?, ?, ?)"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return nil }
        sqlite3_bind_int64(stmt, 1, categoryId)
        sqlite3_bind_text(stmt, 2, (pattern as NSString).utf8String, -1, nil)
        sqlite3_bind_int(stmt, 3, caseInsensitive ? 1 : 0)
        guard sqlite3_step(stmt) == SQLITE_DONE else { sqlite3_finalize(stmt); return nil }
        let id = sqlite3_last_insert_rowid(db)
        sqlite3_finalize(stmt)
        ruleCache = nil
        return id
    }

    func updateRule(id: Int64, pattern: String, caseInsensitive: Bool = true) {
        let sql = "UPDATE rules SET pattern = ?, case_insensitive = ? WHERE id = ?"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
        sqlite3_bind_text(stmt, 1, (pattern as NSString).utf8String, -1, nil)
        sqlite3_bind_int(stmt, 2, caseInsensitive ? 1 : 0)
        sqlite3_bind_int64(stmt, 3, id)
        sqlite3_step(stmt)
        sqlite3_finalize(stmt)
        ruleCache = nil
    }

    func deleteRule(id: Int64) {
        let sql = "DELETE FROM rules WHERE id = ?"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
        sqlite3_bind_int64(stmt, 1, id)
        sqlite3_step(stmt)
        sqlite3_finalize(stmt)
        ruleCache = nil
    }

    // MARK: - Category Resolution (rules-based)

    private var ruleCache: [(catName: String, catColor: String, catId: Int64, pattern: NSRegularExpression)]? = nil

    func resolveCategory(app: String, title: String) -> (name: String, color: String)? {
        if ruleCache == nil { reloadRuleCache() }
        let target = "\(app) \(title)".lowercased()
        for r in ruleCache ?? [] {
            let range = NSRange(target.startIndex..<target.endIndex, in: target)
            if r.pattern.firstMatch(in: target, range: range) != nil {
                return (r.catName, r.catColor)
            }
        }
        return nil
    }

    private func reloadRuleCache() {
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
        ruleCache = cache
    }

    // MARK: - Category Match Preview

    func getCategoryMatches(id: Int64) -> [[String: Any]] {
        let rules = queryRows("SELECT id, pattern, case_insensitive FROM rules WHERE category_id = ?") { stmt in
            sqlite3_bind_int64(stmt, 1, id)
        }
        guard !rules.isEmpty else { return [] }

        var compiled: [NSRegularExpression] = []
        for r in rules {
            guard let pat = r["pattern"] as? String, !pat.isEmpty else { continue }
            let ci = (r["case_insensitive"] as? Int ?? 1) != 0
            if let regex = try? NSRegularExpression(pattern: pat, options: ci ? [.caseInsensitive] : []) {
                compiled.append(regex)
            }
        }

        // 오늘 날짜 범위만 조회 (스택드 바와 일치)
        let (start, end) = parseDate(nil)
        let skipList = skipApps.map { "'\($0)'" }.joined(separator: ",")
        let rows = queryRows("""
            SELECT json_extract(data, '$.app') as app,
                   json_extract(data, '$.title') as title,
                   duration
            FROM events
            WHERE bucket_id = 'aw-watcher-window'
              AND timestamp >= ? AND timestamp <= ?
              AND json_extract(data, '$.app') NOT IN (\(skipList))
              AND json_extract(data, '$.title') IS NOT NULL
              AND json_extract(data, '$.title') != ''
        """) { stmt in
            sqlite3_bind_double(stmt, 1, start)
            sqlite3_bind_double(stmt, 2, end)
        }

        var pairMap: [String: (app: String, title: String, duration: Double)] = [:]
        for row in rows {
            let app = row["app"] as? String ?? ""
            if isSkipped(app) { continue }
            let title = row["title"] as? String ?? ""
            let dur = row["duration"] as? Double ?? 0
            let target = "\(app) \(title)".lowercased()
            let range = NSRange(target.startIndex..<target.endIndex, in: target)
            for regex in compiled {
                if regex.firstMatch(in: target, range: range) != nil {
                    let key = "\(app)|||\(title)"
                    if pairMap[key] != nil {
                        pairMap[key]!.duration += dur
                    } else {
                        pairMap[key] = (app, title, dur)
                    }
                    break
                }
            }
        }

        return pairMap.values.map { ["app": $0.app, "title": $0.title, "duration": $0.duration] }
    }

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

        // 2. 오늘 이벤트 1회 조회
        let (start, end) = parseDate(nil)
        let skipList = skipApps.map { "'\($0)'" }.joined(separator: ",")
        let rows = queryRows("""
            SELECT json_extract(data, '$.app') as app,
                   json_extract(data, '$.title') as title,
                   duration
            FROM events
            WHERE bucket_id = 'aw-watcher-window'
              AND timestamp >= ? AND timestamp <= ?
              AND json_extract(data, '$.app') NOT IN (\(skipList))
              AND json_extract(data, '$.title') IS NOT NULL
              AND json_extract(data, '$.title') != ''
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
            let dur = row["duration"] as? Double ?? 0
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

    /// 어떤 카테고리에도 매칭되지 않는 고유 (app, title) 쌍 반환
    func getUntaggedPairs() -> [[String: Any]] {
        if ruleCache == nil { reloadRuleCache() }
        return getRecentPairs().filter { pair in
            let target = "\(pair["app"] ?? "") \(pair["title"] ?? "")".lowercased()
            for r in ruleCache ?? [] {
                let range = NSRange(target.startIndex..<target.endIndex, in: target)
                if r.pattern.firstMatch(in: target, range: range) != nil {
                    return false
                }
            }
            return true
        }
    }

    /// 최근 N일간 고유 (app, title) 쌍 (중복 제거)
    private func getRecentPairs(days: Int = 7) -> [[String: Any]] {
        let cal = Calendar.current
        guard let startDay = cal.date(byAdding: .day, value: -days, to: Date()) else { return [] }
        let start = cal.startOfDay(for: startDay).timeIntervalSince1970
        let end = Date().timeIntervalSince1970 + 3600 // 약간 여유
        let skipList = skipApps.map { "'\($0)'" }.joined(separator: ",")
        let rows = queryRows("""
            SELECT DISTINCT json_extract(data, '$.app') as app,
                            json_extract(data, '$.title') as title
            FROM events
            WHERE bucket_id = 'aw-watcher-window'
              AND timestamp >= ? AND timestamp <= ?
              AND json_extract(data, '$.app') NOT IN (\(skipList))
              AND json_extract(data, '$.title') IS NOT NULL
              AND json_extract(data, '$.title') != ''
        """) { stmt in
            sqlite3_bind_double(stmt, 1, start)
            sqlite3_bind_double(stmt, 2, end)
        }
        // 부분 문자열 스킵 (SQL NOT IN으로는 대체 불가)
        return rows.filter { !isSkipped($0["app"] as? String ?? "") }
    }

    // MARK: - Tag Stats (regex-based)

    func getTagStats(targetDate: String? = nil) -> [[String: Any]] {
        let (start, end) = parseDate(targetDate)
        let skipList = skipApps.map { "'\($0)'" }.joined(separator: ",")
        let rows = queryRows("""
            SELECT json_extract(data, '$.app') as app,
                   json_extract(data, '$.title') as title,
                   duration
            FROM events
            WHERE bucket_id = 'aw-watcher-window'
              AND timestamp >= ? AND timestamp <= ?
              AND json_extract(data, '$.app') NOT IN (\(skipList))
        """) { stmt in
            sqlite3_bind_double(stmt, 1, start)
            sqlite3_bind_double(stmt, 2, end)
        }

        var pairMap: [String: (app: String, title: String, dur: Double)] = [:]
        for r in rows {
            let app = r["app"] as? String ?? ""
            if isSkipped(app) { continue } // 부분 문자열 스킵은 코드에서 처리
            let title = r["title"] as? String ?? ""
            let dur = r["duration"] as? Double ?? 0
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
            if let cat = resolveCategory(app: pair.app, title: pair.title) {
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

    func getWeeklyTagStats() -> [[String: Any]] {
        let cal = Calendar.current
        let formatter = DateFormatter()
        formatter.calendar = cal
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        var result: [[String: Any]] = []
        for dayOffset in (0..<7).reversed() {
            guard let day = cal.date(byAdding: .day, value: -dayOffset, to: Date()) else { continue }
            let dateStr = formatter.string(from: day)
            let dayName: String
            let weekday = cal.component(.weekday, from: day)
            let dayNames = ["일", "월", "화", "수", "목", "금", "토"]
            dayName = dayNames[weekday - 1]

            let stats = getTagStats(targetDate: dateStr)
            let tags = stats.filter { $0["tag"] as? String != "__untagged__" }
            var taggedTotal: Double = 0
            var dayTags: [[String: Any]] = []
            for t in tags {
                let secs = t["seconds"] as? Double ?? 0
                taggedTotal += secs
                dayTags.append(t)
            }
            let untaggedSecs = stats.last?["seconds"] as? Double ?? 0
            result.append([
                "date": dateStr, "day": dayName,
                "tags": dayTags,
                "tagged_seconds": taggedTotal,
                "untagged_seconds": untaggedSecs,
                "total_seconds": taggedTotal + untaggedSecs
            ])
        }
        return result
    }
}
