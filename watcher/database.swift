import Foundation
import SQLite3

// MARK: - Database

class Database {
    static let shared = Database()
    var db: OpaquePointer?
    let dbPath: String

    private init() {
        dbPath = (FileManager.default.homeDirectoryForCurrentUser.path
            as NSString).appendingPathComponent(".mactimetracker/aw.db")
        let dir = (dbPath as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir,
            withIntermediateDirectories: true)
        open()
    }

    deinit {
        if let db = db { sqlite3_close(db) }
    }

    private func open() {
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
        """)
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

    private let skipApps: Set<String> = ["loginwindow", "WindowServer", "SystemUIServer", "Dock", "Spotlight", "NotificationCenter"]
    private let browserApps: Set<String> = ["Brave Browser", "Google Chrome", "Safari", "Firefox",
        "Microsoft Edge", "Arc", "Orion", "Opera", "Opera GX", "Vivaldi", "Tor Browser"]

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
            let hour = String(format: "%02d:00", Int(Date(timeIntervalSince1970: ts).timeIntervalSince1970 / 3600) % 24)
            hourly[hour, default: [:]][app, default: 0] += dur
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
            if skipApps.contains(app) { continue }
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
            if !skipApps.contains(app) {
                currentApp = app
                currentTitle = data["title"]
                break
            }
        }

        return TodayInfo(totalSeconds: total, apps: sortedApps, currentApp: currentApp, currentTitle: currentTitle)
    }

    private func todayISO() -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]
        return formatter.string(from: Date())
    }
}
