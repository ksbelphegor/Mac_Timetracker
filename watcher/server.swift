import Foundation
import Network
import UniformTypeIdentifiers
import ImageIO
import AppKit
import os

// MARK: - HTTP Server (NWListener)

class HTTPServer {
    let port: UInt16
    var listener: NWListener?
    let queue = DispatchQueue(label: "http-server", qos: .background)
    let db = Database.shared
    let logger = Logger(subsystem: "com.jsk.mactimetracker", category: "server")

    private let staticDir: String

    // 앱 아이콘 캐시 { 앱이름: PNG Data } — thread-safe 보장을 위해 별도 lock
    private let iconCache = NSCache<NSString, NSData>()
    private let iconCacheLock = NSLock()
    // NSCache의 totalCostLimit: byte-cost 기반
    private func initIconCache() {
        iconCacheLock.lock()
        iconCache.countLimit = 200  // 객체 개수 상한
        iconCacheLock.unlock()
    }

    init(port: UInt16 = 8000) {
        self.port = port
        // 번들 리소스 우선, 없으면 개발 경로 fallback
        if let resPath = Bundle.main.resourcePath {
            staticDir = (resPath as NSString).appendingPathComponent("dashboard/static")
        } else {
            let scriptDir = ((#file as NSString).deletingLastPathComponent as NSString).deletingLastPathComponent
            staticDir = (scriptDir as NSString).appendingPathComponent("dashboard/static")
        }
        initIconCache()
    }

    func start() {
        guard let listener = try? NWListener(using: .tcp, on: NWEndpoint.Port(rawValue: port)!) else {
            self.logger.error("HTTP server: failed to start on port \(self.port)")
            return
        }
        self.listener = listener
        listener.stateUpdateHandler = { state in
            if case .ready = state { self.logger.log("HTTP server: ready on :\(self.port)") }
            if case .failed(let err) = state { self.logger.error("HTTP server: failed - \(err)") }
        }
        listener.newConnectionHandler = { [weak self] conn in
            conn.start(queue: self?.queue ?? .global())
            self?.handle(conn)
        }
        listener.start(queue: queue)
    }

    func stop() {
        listener?.cancel()
        listener = nil
    }

    // MARK: - Connection handling

    private let maxRequestSize = 1_000_000

    private func handle(_ conn: NWConnection) {
        // 🔒 루프백 전용: LAN(같은 Wi-Fi)의 다른 기기는 대시보드/API에 접근 불가
        //   (이유: 앱 사용기록·창 제목·URL·규칙이 그대로 노출되므로)
        if !Self.isLoopback(conn.endpoint) {
            logger.log("⛔ 접속 거절 (loopback-only): \(conn.endpoint.debugDescription)")
            conn.cancel()
            return
        }
        pump(conn, buffer: Data())
    }

    /// 원격 peer가 loopback(127.0.0.1 / ::1 / localhost)인지 확인
    private static func isLoopback(_ ep: NWEndpoint?) -> Bool {
        guard let ep else { return false }
        if case .hostPort(let host, _) = ep {
            switch host {
            case .name(let n, _):
                return ["127.0.0.1", "::1", "localhost"].contains(n)
            case .ipv4(let a):
                return a.isLoopback
            case .ipv6(let a):
                return a.isLoopback
            @unknown default:
                return false
            }
        }
        return false
    }

    /// 요청 완결(헤더 끝 + Content-Length 만큼 body 수신)될 때까지 receive 반복.
    /// 일부만 받은 요청으로 400을 답거나 body를 떨어트리는 문제를 방지.
    /// NWConnection.receive은 비동기(콜백)이라 재귀가 불가피. request body가
    /// 1KB 이하(heartbeat 등)인 현재 워크로드에선 stack 깊이가 아니므로 유지.
    /// maxRequestSize(1MB) 상한 + 413 처리로 unbounded grow 방지.
    private func pump(_ conn: NWConnection, buffer: Data) {
        var buffer = buffer
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, _, error in
            guard let self = self else { conn.cancel(); return }
            if let d = data { buffer.append(d) }
            if buffer.count > self.maxRequestSize {
                let resp = Response.json(413, ["error": "Payload Too Large"])
                conn.send(content: resp.data, completion: .contentProcessed { _ in conn.cancel() })
                return
            }
            if let req = Self.parseComplete(buffer) {
                let response = self.processRequest(req)
                conn.send(content: response.data, completion: .contentProcessed { _ in conn.cancel() })
                return
            }
            if error != nil { conn.cancel(); return }
            self.pump(conn, buffer: buffer)
        }
    }

    // MARK: - Request parsing

    struct Request {
        let method: String
        let path: String
        let query: [String: String]
        let body: Data?
    }

    /// 버퍼에서 요청을 파싱 (byte 기반 — UTF-8 멀티바이트 안전).
    /// 헤더 끝(\r\n\r\n)과 Content-Length만큼 body를 모두 받을 때까지 nil 반환 (계속 receive).
    private static func parseComplete(_ buf: Data) -> Request? {
        // \r\n\r\n 바이트 시퀀스 탐색
        let eol: [UInt8] = [0x0d, 0x0a, 0x0d, 0x0a]
        var headerEnd: Int? = nil
        if buf.count >= 4 {
            outer: for i in 0...(buf.count - 4) {
                for j in 0..<4 where buf[i + j] != eol[j] { continue outer }
                headerEnd = i + 4
                break
            }
        }
        guard let hEnd = headerEnd else {
            return buf.count < 8192 ? nil : parseRaw(buf)  // 비정상적으로 긴 헤더는 마지막에 파싱
        }

        let headStr = String(data: buf.prefix(hEnd), encoding: .utf8) ?? ""
        let lines = headStr.components(separatedBy: "\r\n")
        guard lines.count >= 1 else { return nil }
        let requestLine = lines[0].components(separatedBy: " ")
        guard requestLine.count >= 2 else { return nil }

        var contentLength = 0
        for i in 1..<lines.count {
            let line = lines[i]
            if line.isEmpty { break }
            if let colon = line.firstIndex(of: ":") {
                let key = line[line.startIndex..<colon].lowercased()
                let val = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
                if key == "content-length" { contentLength = Int(val) ?? 0 }
            }
        }
        if contentLength > 0, buf.count < hEnd + contentLength { return nil }  // body 도착 중

        let body: Data
        if contentLength > 0 {
            body = buf.subdata(in: hEnd..<(hEnd + contentLength))
        } else {
            body = Data()
        }

        let method = requestLine[0]
        var fullPath = requestLine[1]
        var query: [String: String] = [:]
        if let qIdx = fullPath.firstIndex(of: "?") {
            let qStr = fullPath[qIdx...].dropFirst()
            fullPath = String(fullPath[..<qIdx])
            for pair in qStr.split(separator: "&") {
                let kv = pair.split(separator: "=", maxSplits: 1)
                if kv.count == 2 {
                    let key = String(kv[0]).removingPercentEncoding ?? String(kv[0])
                    let val = String(kv[1]).removingPercentEncoding ?? String(kv[1])
                    query[key] = val
                }
            }
        }
        return Request(method: method.uppercased(), path: fullPath, query: query, body: body)
    }

    /// 완결 여부를 모르는(예: 누락된 헤더 끝) 요청을 그대로 파싱
    private static func parseRaw(_ buf: Data) -> Request? {
        guard let raw = String(data: buf, encoding: .utf8) else { return nil }
        let lines = raw.components(separatedBy: "\r\n")
        guard lines.count >= 1 else { return nil }
        let requestLine = lines[0].components(separatedBy: " ")
        guard requestLine.count >= 2 else { return nil }

        var contentLength = 0
        var headerDone = false
        for i in 1..<min(lines.count, 32) {
            let line = lines[i]
            if line.isEmpty { headerDone = true; break }
            if let colon = line.firstIndex(of: ":") {
                let key = line[line.startIndex..<colon].lowercased()
                let val = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
                if key == "content-length" { contentLength = Int(val) ?? 0 }
            }
        }

        let body: Data?
        if headerDone, let sepIdx = raw.range(of: "\r\n\r\n") {
            let bodyHave = raw.distance(from: sepIdx.upperBound, to: raw.endIndex)
            let take = min(contentLength, bodyHave)
            body = take > 0 ? String(raw[sepIdx.upperBound...]).prefix(take).data(using: .utf8) : Data()
        } else {
            body = nil
        }

        let method = requestLine[0]
        var fullPath = requestLine[1]
        var query: [String: String] = [:]
        if let qIdx = fullPath.firstIndex(of: "?") {
            let qStr = fullPath[qIdx...].dropFirst()
            fullPath = String(fullPath[..<qIdx])
            for pair in qStr.split(separator: "&") {
                let kv = pair.split(separator: "=", maxSplits: 1)
                if kv.count == 2 {
                    let key = String(kv[0]).removingPercentEncoding ?? String(kv[0])
                    let val = String(kv[1]).removingPercentEncoding ?? String(kv[1])
                    query[key] = val
                }
            }
        }
        return Request(method: method.uppercased(), path: fullPath, query: query, body: body)
    }

    // MARK: - Response building

    struct Response {
        let status: Int
        let headers: [String: String]
        let body: Data

        var data: Data {
            var resp = "HTTP/1.1 \(status) \(statusText)\r\n"
            var allHeaders = headers
            allHeaders["Content-Length"] = "\(body.count)"
            allHeaders["Connection"] = "close"
            allHeaders["Access-Control-Allow-Origin"] = "*"
            for (k, v) in allHeaders {
                resp += "\(k): \(v)\r\n"
            }
            resp += "\r\n"
            var result = Data(resp.utf8)
            result.append(body)
            return result
        }

        var statusText: String {
            switch status {
            case 200: return "OK"
            case 201: return "Created"
            case 204: return "No Content"
            case 400: return "Bad Request"
            case 404: return "Not Found"
            case 405: return "Method Not Allowed"
            case 500: return "Internal Server Error"
            default: return "Unknown"
            }
        }

        static func json(_ status: Int, _ body: Any) -> Response {
            let data = (try? JSONSerialization.data(withJSONObject: body, options: [.withoutEscapingSlashes])) ?? Data()
            return Response(status: status, headers: ["Content-Type": "application/json; charset=utf-8"], body: data)
        }

        static func html(_ status: Int, _ html: String) -> Response {
            Response(status: status, headers: ["Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-cache, no-store, must-revalidate"], body: Data(html.utf8))
        }

        static func file(_ path: String) -> Response {
            let url = URL(fileURLWithPath: path)
            guard let attrs = try? FileManager.default.attributesOfItem(atPath: path),
                  let data = try? Data(contentsOf: url) else {
                return .json(404, ["error": "Not Found"])
            }
            let ext = (path as NSString).pathExtension.lowercased()
            let mime: String
            switch ext {
            case "html": mime = "text/html; charset=utf-8"
            case "css": mime = "text/css"
            case "js": mime = "application/javascript"
            case "png": mime = "image/png"
            case "jpg", "jpeg": mime = "image/jpeg"
            case "svg": mime = "image/svg+xml"
            case "json": mime = "application/json"
            case "ico": mime = "image/x-icon"
            default: mime = "application/octet-stream"
            }
            var headers: [String: String] = ["Content-Type": mime]
            // HTML: 매 요청 검증(노출 바꾸면) + ETag
            // 정적 자원은 mtime 기반 ETag + 1h 캐시
            if let mtime = attrs[.modificationDate] as? Date {
                let etag = "\(Int(mtime.timeIntervalSince1970))-\(data.count)"
                headers["ETag"] = etag
                if ext == "html" {
                    headers["Cache-Control"] = "no-cache"
                } else {
                    headers["Cache-Control"] = "max-age=3600" + (ext == "js" || ext == "css" ? ", public" : "")
                }
            } else {
                headers["Cache-Control"] = ext == "html" ? "no-cache" : "max-age=3600"
            }
            return Response(status: 200, headers: headers, body: data)
        }
    }

    // MARK: - Permissions (대시보드 설정 패널)

    private func handlePermissionsStatus(_ req: Request) -> Response {
        guard let app = NSApp.delegate as? AppDelegate else {
            return .json(200, ["screen_recording": false, "accessibility": false, "all_ok": false, "checked_at": 0, "app_found": false])
        }
        let s = app.permissionSnapshot
        let srReq = app.srRequired
        return .json(200, [
            "screen_recording": s.sr,
            "accessibility": s.ax,
            "sr_required": srReq,
            "all_ok": s.ax && (!srReq || s.sr),
            "checked_at": Int(s.at.timeIntervalSince1970),
            "app_found": true
        ])
    }

    private func handlePermissionsAction(_ req: Request) -> Response {
        guard let app = NSApp.delegate as? AppDelegate else {
            return .json(503, ["error": "App delegate unavailable"])
        }
        let action = req.query["action"] ?? "check"
        let which = req.query["which"] ?? ""
        switch action {
        case "check":
            // Silent 재확인 (프롬프트 없음) — 결과 반영은 60s 모니터/다음 폴링에서
            DispatchQueue.main.async { app.refreshPermissionStatus() }
        case "prompt":
            // 시스템 TCC 프롬프트 표시 (사용자 명시적 요청)
            app.promptForPermission(which)
        case "settings":
            // 시스템 설정 개인정보 보호 패널 열기
            DispatchQueue.main.async { app.openSettingsPane(which) }
        default:
            return .json(400, ["error": "Unknown action: \(action)"])
        }
        let s = app.permissionSnapshot
        let srReq = app.srRequired
        return .json(200, [
            "triggered": true,
            "screen_recording": s.sr,
            "accessibility": s.ax,
            "sr_required": srReq,
            "all_ok": s.ax && (!srReq || s.sr),
            "checked_at": Int(s.at.timeIntervalSince1970)
        ])
    }

    // MARK: - Router (API handlers)

    private func processRequest(_ req: Request) -> Response {
        let path = req.path

        // API Routes
        if path == "/api/ping" && req.method == "GET" {
            return .json(200, ["ok": true])
        }
        if path == "/api/heartbeat" && req.method == "POST" {
            return handleHeartbeat(req)
        }
        if path == "/api/today" && req.method == "GET" {
            return handleToday(req)
        }
        if path == "/api/permissions" && req.method == "GET" {
            return handlePermissionsStatus(req)
        }
        if path == "/api/permissions" && req.method == "POST" {
            return handlePermissionsAction(req)
        }
        if path == "/api/browser-sessions" && req.method == "GET" {
            return handleBrowserSessions(req)
        }
        if path == "/api/categories" && req.method == "GET" {
            return handleGetCategories(req)
        }
        if path == "/api/categories" && req.method == "POST" {
            return handleCreateCategory(req)
        }
        if path.hasPrefix("/api/categories/") && req.method == "PATCH" {
            let prefix = "/api/categories/"
            let idStr = String(path.dropFirst(prefix.count)).removingPercentEncoding ?? ""
            if let id = Int64(idStr) { return handleUpdateCategory(req, id: id) }
            return .json(400, ["error": "Invalid id"])
        }
        if path.hasPrefix("/api/categories/") && req.method == "DELETE" {
            let prefix = "/api/categories/"
            let idStr = String(path.dropFirst(prefix.count)).removingPercentEncoding ?? ""
            if let id = Int64(idStr) { return handleDeleteCategory(id: id) }
            return .json(400, ["error": "Invalid id"])
        }
        if path == "/api/category-all-matches" && req.method == "GET" {
            return handleCategoryAllMatches()
        }
        if path == "/api/rules" && req.method == "POST" {
            return handleCreateRule(req)
        }
        if path.hasPrefix("/api/rules/") && req.method == "PATCH" {
            let idStr = String(path.dropFirst("/api/rules/".count))
            if let id = Int64(idStr) { return handleUpdateRule(req, id: id) }
            return .json(400, ["error": "Invalid id"])
        }
        if path.hasPrefix("/api/rules/") && req.method == "DELETE" {
            let idStr = String(path.dropFirst("/api/rules/".count))
            if let id = Int64(idStr) { return handleDeleteRule(id: id) }
            return .json(400, ["error": "Invalid id"])
        }
        if path == "/api/tag-stats" && req.method == "GET" {
            return handleTagStats(req)
        }
        if path.hasPrefix("/api/sessions/") && req.method == "GET" {
            let prefix = "/api/sessions/"
            let appName = String(path.dropFirst(prefix.count))
                .removingPercentEncoding ?? String(path.dropFirst(prefix.count))
            return handleAppSessions(req, appName: appName)
        }
        if path.hasPrefix("/api/app-icon/") && req.method == "GET" {
            let prefix = "/api/app-icon/"
            let appName = String(path.dropFirst(prefix.count))
                .removingPercentEncoding ?? String(path.dropFirst(prefix.count))
            return handleAppIcon(appName: appName)
        }

        // Static files
        if path == "/" || path == "" {
            let indexPath = (staticDir as NSString).appendingPathComponent("index.html")
            return .file(indexPath)
        }
        if path.hasPrefix("/static/") {
            let staticPrefix = "/static/"
            let relPath = String(path.dropFirst(staticPrefix.count))
            let filePath = (staticDir as NSString).appendingPathComponent(relPath)
            // Path traversal 방어: 실제 경로가 staticDir 내부에 있는지 확인
            let resolved = (filePath as NSString).standardizingPath
            let base = (staticDir as NSString).standardizingPath
            if !resolved.hasPrefix(base + "/") && resolved != base {
                return .json(404, ["error": "Not Found"])
            }
            return .file(filePath)
        }

        return .json(404, ["error": "Not Found"])
    }

    // MARK: - API Handlers

    private func handleHeartbeat(_ req: Request) -> Response {
        guard let body = req.body,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let timestamp = json["timestamp"] as? Double else {
            return .json(400, ["error": "Invalid heartbeat"])
        }
        let duration = json["duration"] as? Double ?? 0
        let rawData = json["data"] as? [String: Any] ?? [:]
        // AppKit에서 보내는 data는 [String: String]이지만 안전하게 serialize
        let dataStr = (try? JSONSerialization.data(withJSONObject: rawData, options: []))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        db.insertHeartbeat(timestamp: timestamp, duration: max(duration, 1.0), data: dataStr)
        return .json(200, ["status": "ok"])
    }

    private func handleToday(_ req: Request) -> Response {
        let targetDate = req.query["target_date"]
        let info = db.getTodayInfo(targetDate: targetDate)
        let apps = info.apps.map { app -> [String: Any] in
            ["name": app.name, "seconds": app.seconds, "last_title": app.lastTitle]
        }
        return .json(200, [
            "total_seconds": info.totalSeconds,
            "apps": apps,
            "current_app": info.currentApp as Any,
            "current_title": info.currentTitle as Any
        ])
    }

    // (dead API handler 제거됨: recent/summary/hourly/now — 대시보드 미사용)

    private func handleBrowserSessions(_ req: Request) -> Response {
        let sessions = db.buildSessions(browserOnly: true, targetDate: req.query["target_date"])
        return .json(200, ["sessions": sessions])
    }

    // MARK: - Categories API

    private func handleGetCategories(_ req: Request) -> Response {
        return .json(200, db.getCategories())
    }

    private func handleCreateCategory(_ req: Request) -> Response {
        guard let body = req.body,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let name = (json["name"] as? String)?.trimmingCharacters(in: .whitespaces),
              !name.isEmpty else {
            return .json(400, ["error": "Missing name"])
        }
        let color = json["color"] as? String ?? "#58a6ff"
        let regex = json["regex"] as? String ?? ""
        let parentId = json["parent_id"] as? Int64
        let score = json["score"] as? Int ?? 0
        if let id = db.createCategory(name: name, color: color, regex: regex, parentId: parentId, score: score) {
            return .json(201, ["id": id, "status": "created"])
        }
        return .json(500, ["error": "Create failed"])
    }

    private func handleUpdateCategory(_ req: Request, id: Int64) -> Response {
        guard let body = req.body,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let name = (json["name"] as? String)?.trimmingCharacters(in: .whitespaces),
              !name.isEmpty else {
            return .json(400, ["error": "Missing name"])
        }
        let color = json["color"] as? String ?? "#58a6ff"
        let regex = json["regex"] as? String ?? ""
        let parentId = json["parent_id"] as? Int64
        let sortOrder = json["sort_order"] as? Int ?? 0
        let score = json["score"] as? Int ?? 0
        db.updateCategory(id: id, name: name, color: color, regex: regex, parentId: parentId, sortOrder: sortOrder, score: score)
        return .json(200, ["status": "ok"])
    }

    private func handleDeleteCategory(id: Int64) -> Response {
        db.deleteCategory(id: id)
        return .json(200, ["status": "ok"])
    }

    private func handleCategoryAllMatches() -> Response {
        let allMatches = db.getAllCategoryMatches()
        return .json(200, allMatches)
    }

    // MARK: - Rules API

    private func handleCreateRule(_ req: Request) -> Response {
        guard let body = req.body,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let categoryId = json["category_id"] as? Int64,
              let pattern = (json["pattern"] as? String)?.trimmingCharacters(in: .whitespaces),
              !pattern.isEmpty else {
            return .json(400, ["error": "Missing category_id or pattern"])
        }
        let ci = json["case_insensitive"] as? Bool ?? true
        if let id = db.createRule(categoryId: categoryId, pattern: pattern, caseInsensitive: ci) {
            return .json(201, ["id": id, "status": "created"])
        }
        return .json(500, ["error": "Create failed"])
    }

    private func handleUpdateRule(_ req: Request, id: Int64) -> Response {
        guard let body = req.body,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let pattern = (json["pattern"] as? String)?.trimmingCharacters(in: .whitespaces),
              !pattern.isEmpty else {
            return .json(400, ["error": "Missing pattern"])
        }
        let ci = json["case_insensitive"] as? Bool ?? true
        db.updateRule(id: id, pattern: pattern, caseInsensitive: ci)
        return .json(200, ["status": "ok"])
    }

    private func handleDeleteRule(id: Int64) -> Response {
        db.deleteRule(id: id)
        return .json(200, ["status": "ok"])
    }

    // MARK: - Tag Stats

    private func handleTagStats(_ req: Request) -> Response {
        let stats = db.getTagStats(targetDate: req.query["target_date"])
        return .json(200, stats)
    }

    private func handleAppSessions(_ req: Request, appName: String) -> Response {
        let sessions = db.buildSessions(appFilter: appName, targetDate: req.query["target_date"])
        return .json(200, ["app": appName, "sessions": sessions])
    }

    // MARK: - App Icon

    private func handleAppIcon(appName: String) -> Response {
        guard let pngData = iconData(for: appName) else {
            return .json(404, ["error": "Icon not found"])
        }
        return Response(status: 200,
            headers: ["Content-Type": "image/png", "Cache-Control": "max-age=86400"],
            body: pngData)
    }

    private func iconData(for appName: String) -> Data? {
        // Cache check (lock으로 thread-safe)
        let key = appName.lowercased() as NSString
        iconCacheLock.lock()
        if let cached = iconCache.object(forKey: key) { iconCacheLock.unlock(); return cached as Data }
        iconCacheLock.unlock()

        // 한글 시스템 앱 → 영문 번들명 매핑 (fullPath가 한글명을 못 찾는 경우 대비)
        let engFallback: [String: String] = [
            "메모": "Notes",
            "시스템 설정": "System Settings",
            "시스템 환경설정": "System Preferences",
            "파인더": "Finder",
            "사파리": "Safari",
            "미리보기": "Preview",
            "메시지": "Messages",
            "미리 알림": "Reminders",
            "캘린더": "Calendar",
            "주소록": "Contacts",
            "음악": "Music",
            "사진": "Photos",
            "지도": "Maps",
            "번역": "Translate",
            "단축어": "Shortcuts",
            "스티커": "Stickies",
            "터미널": "Terminal",
            "콘솔": "Console",
            "활성 상태 보기": "Activity Monitor",
        ]

        var pngData: Data?
        // NSWorkspace.icon 호출은 메인 스레드 — AppKit 아이콘 API는 메인에서만 안전.
        // 메인에서 호출 시엔 직접, 배경 스레드에선 main.async + sem + 0.5s timeout.
        func loadIcon() {
            let ws = NSWorkspace.shared
            var icon: NSImage?

            // 1. 실행 중인 앱에서 아이콘 가져오기 (localizedName 매칭)
            if let app = ws.runningApplications.first(where: { $0.localizedName == appName }) {
                icon = app.icon
            }

            // 2. 실행 중인 앱을 영문명으로도 시도
            if icon == nil, let eng = engFallback[appName] {
                if let app = ws.runningApplications.first(where: { $0.localizedName == eng }) {
                    icon = app.icon
                }
            }

            // 3. 앱 번들 경로 찾아서 아이콘 가져오기 (localized name)
            if icon == nil, let appPath = ws.fullPath(forApplication: appName) {
                icon = ws.icon(forFile: appPath)
            }

            // 4. 영문 fallback으로 번들 경로 재시도
            if icon == nil, let eng = engFallback[appName],
               let appPath = ws.fullPath(forApplication: eng) {
                icon = ws.icon(forFile: appPath)
            }

            guard let srcIcon = icon else { return }

            // 5. 20x20 PNG 렌더 (bitmap context — NSWorkspace.icon에만 main 필요)
            let size = 20
            guard let cg = srcIcon.cgImage(forProposedRect: nil, context: nil, hints: nil),
                  let ctx = CGContext(data: nil, width: size, height: size,
                                      bitsPerComponent: 8, bytesPerRow: 0,
                                      space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return }
            ctx.interpolationQuality = .high
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: size, height: size))
            guard let out = ctx.makeImage() else { return }
            let data = NSMutableData()
            if let dest = CGImageDestinationCreateWithData(data as CFMutableData,
                                                           UTType.png.identifier as CFString, 1, nil) {
                CGImageDestinationAddImage(dest, out, nil)
                CGImageDestinationFinalize(dest)
                pngData = data as Data
            }
        }

        // AppKit 아이콘 API는 메인 스레드에서만 안전 → non-main 시 main async + sem.
        // 모달 루프 갇힘 방지: timeout(0.5s) 실패 시 다음 요청에서 재시도.
        // (main.sync 금지 — NSAlert 등으로 메인 블로킹 시 데드락)
        if Thread.isMainThread {
            loadIcon()
        } else {
            let sem = DispatchSemaphore(value: 0)
            DispatchQueue.main.async {
                loadIcon()
                sem.signal()
            }
            _ = sem.wait(timeout: .now() + 0.5)
        }

        // 유효한 아이콘만 캐시 (너무 작으면 기본 문서 아이콘 → 무시)
        if let d = pngData, d.count > 200 {
            iconCacheLock.lock()
            iconCache.setObject(d as NSData, forKey: key)
            iconCacheLock.unlock()
            return d
        }
        return nil
    }
}
