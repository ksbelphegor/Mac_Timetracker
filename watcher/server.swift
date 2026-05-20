import Foundation
import Network

// MARK: - HTTP Server (NWListener)

class HTTPServer {
    let port: UInt16
    var listener: NWListener?
    let queue = DispatchQueue(label: "http-server", qos: .background)
    let db = Database.shared

    private let staticDir: String

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
}
