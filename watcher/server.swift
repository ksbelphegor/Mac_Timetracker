import Foundation
import Network
import UniformTypeIdentifiers
import ImageIO
import AppKit

// MARK: - HTTP Server (NWListener)

class HTTPServer {
    let port: UInt16
    var listener: NWListener?
    let queue = DispatchQueue(label: "http-server", qos: .background)
    let db = Database.shared

    private let staticDir: String

    // 앱 아이콘 캐시 { 앱이름: PNG Data }
    private var iconCache = NSCache<NSString, NSData>()

    init(port: UInt16 = 8000) {
        self.port = port
        // 번들 리소스 우선, 없으면 개발 경로 fallback
        if let resPath = Bundle.main.resourcePath {
            staticDir = (resPath as NSString).appendingPathComponent("dashboard/static")
        } else {
            let scriptDir = ((#file as NSString).deletingLastPathComponent as NSString).deletingLastPathComponent
            staticDir = (scriptDir as NSString).appendingPathComponent("dashboard/static")
        }
    }

    func start() {
        guard let listener = try? NWListener(using: .tcp, on: NWEndpoint.Port(rawValue: port)!) else {
            print("HTTP server: failed to start on port \(port)")
            return
        }
        self.listener = listener
        listener.stateUpdateHandler = { state in
            if case .ready = state { print("HTTP server: ready on :\(self.port)") }
            if case .failed(let err) = state { print("HTTP server: failed - \(err)") }
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

    private func handle(_ conn: NWConnection) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, _, error in
            guard let self = self, let data = data, error == nil else {
                conn.cancel()
                return
            }
            let response = self.processRequest(data)
            conn.send(content: response.data, completion: .contentProcessed { _ in conn.cancel() })
        }
    }

    // MARK: - Request parsing

    struct Request {
        let method: String
        let path: String
        let query: [String: String]
        let body: Data?
    }

    private func parseRequest(_ data: Data) -> Request? {
        guard let raw = String(data: data, encoding: .utf8) else { return nil }
        let lines = raw.components(separatedBy: "\r\n")
        guard lines.count >= 1 else { return nil }
        let requestLine = lines[0].components(separatedBy: " ")
        guard requestLine.count >= 2 else { return nil }

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

        // Naive body extraction (split by \r\n\r\n)
        let parts = raw.components(separatedBy: "\r\n\r\n")
        let body: Data? = parts.count >= 2 ? parts.dropFirst().joined(separator: "\r\n\r\n").data(using: .utf8) : nil

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
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)) else {
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
            return Response(status: 200, headers: ["Content-Type": mime,
                "Cache-Control": "no-cache, no-store, must-revalidate"], body: data)
        }
    }

    // MARK: - Router

    private func processRequest(_ data: Data) -> Response {
        guard let req = parseRequest(data) else {
            return .json(400, ["error": "Bad Request"])
        }

        let path = req.path

        // API Routes
        if path == "/api/heartbeat" && req.method == "POST" {
            return handleHeartbeat(req)
        }
        if path == "/api/today" && req.method == "GET" {
            return handleToday(req)
        }
        if path == "/api/recent" && req.method == "GET" {
            return handleRecent(req)
        }
        if path == "/api/summary" && req.method == "GET" {
            return handleSummary(req)
        }
        if path == "/api/hourly" && req.method == "GET" {
            return handleHourly(req)
        }
        if path == "/api/browser-sessions" && req.method == "GET" {
            return handleBrowserSessions(req)
        }
        if path == "/api/now" && req.method == "GET" {
            return handleNow(req)
        }
        if path.hasPrefix("/api/sessions/") && req.method == "GET" {
            let appName = String(path.dropFirst(14))
                .removingPercentEncoding ?? String(path.dropFirst(14))
            return handleAppSessions(req, appName: appName)
        }
        if path.hasPrefix("/api/app-icon/") && req.method == "GET" {
            let appName = String(path.dropFirst(14))
                .removingPercentEncoding ?? String(path.dropFirst(14))
            return handleAppIcon(appName: appName)
        }

        // Static files
        if path == "/" || path == "" {
            let indexPath = (staticDir as NSString).appendingPathComponent("index.html")
            return .file(indexPath)
        }
        if path.hasPrefix("/static/") {
            let relPath = String(path.dropFirst(8))
            let filePath = (staticDir as NSString).appendingPathComponent(relPath)
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
        let data = json["data"] as? [String: Any] ?? [:]
        let dataStr = (try? JSONSerialization.data(withJSONObject: data, options: []))
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

    private func handleRecent(_ req: Request) -> Response {
        let limit = Int(req.query["limit"] ?? "20") ?? 20
        let events = db.getTodayEvents(targetDate: req.query["target_date"])
        let recent = events.suffix(limit).reversed().compactMap { e -> [String: Any]? in
            guard let dataStr = e["data"] as? String,
                  let data = try? JSONSerialization.jsonObject(with: dataStr.data(using: .utf8)!) as? [String: String] else { return nil }
            return [
                "time": e["timestamp"] as! Double,
                "app": data["app"] ?? "Unknown",
                "title": data["title"] ?? "",
                "duration": e["duration"] as! Double
            ]
        }
        return .json(200, ["events": recent])
    }

    private func handleSummary(_ req: Request) -> Response {
        let rows = db.getAppSummary(startDate: req.query["start"], endDate: req.query["end"])
        return .json(200, ["rows": rows])
    }

    private func handleHourly(_ req: Request) -> Response {
        let hourly = db.getHourlyBreakdown(targetDate: req.query["target_date"])
        return .json(200, hourly)
    }

    private func handleBrowserSessions(_ req: Request) -> Response {
        let sessions = db.buildSessions(browserOnly: true, targetDate: req.query["target_date"])
        return .json(200, ["sessions": sessions])
    }

    private func handleNow(_ req: Request) -> Response {
        let events = db.getTodayEvents(targetDate: req.query["target_date"])
        guard let last = events.last else {
            return .json(200, ["app": nil, "since": nil])
        }
        guard let dataStr = last["data"] as? String,
              let data = try? JSONSerialization.jsonObject(with: dataStr.data(using: .utf8)!) as? [String: String] else {
            return .json(200, ["app": nil, "since": nil])
        }
        return .json(200, [
            "app": data["app"] as Any,
            "title": data["title"] as Any,
            "since": last["timestamp"] as Any
        ])
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
        // Cache check
        let key = appName.lowercased() as NSString
        if let cached = iconCache.object(forKey: key) { return cached as Data }

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
        DispatchQueue.main.sync {
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

            // 5. 20x20 PNG로 리사이즈
            let size = NSSize(width: 20, height: 20)
            let resized = NSImage(size: size)
            resized.lockFocusFlipped(false)
            srcIcon.draw(in: NSRect(origin: .zero, size: size),
                         from: NSRect(origin: .zero, size: srcIcon.size),
                         operation: .copy, fraction: 1.0)
            resized.unlockFocus()

            // 6. PNG 데이터로 변환
            guard let cgImage = resized.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }
            let data = NSMutableData()
            if let dest = CGImageDestinationCreateWithData(data as CFMutableData,
                                                           UTType.png.identifier as CFString, 1, nil) {
                CGImageDestinationAddImage(dest, cgImage, nil)
                CGImageDestinationFinalize(dest)
                pngData = data as Data
            }
        }

        // 유효한 아이콘만 캐시 (너무 작으면 기본 문서 아이콘 → 무시)
        if let d = pngData, d.count > 200 {
            iconCache.setObject(d as NSData, forKey: key)
            return d
        }
        return nil
    }
}
