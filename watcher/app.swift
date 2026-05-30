import Cocoa
import Foundation
import ApplicationServices
import os

// MARK: - Configuration

enum Config {
    static let serverURL = "http://localhost:8000"
    static let heartbeatInterval: TimeInterval = 3
    static let statsRefreshInterval: TimeInterval = 60
    static let windowTitleCacheTTL: TimeInterval = 5

    static let browserScripts: [String: String] = [
        "Brave Browser": "tell application \"Brave Browser\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "Google Chrome": "tell application \"Google Chrome\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "Safari": "tell application \"Safari\"\nset t to name of front document\nset u to URL of front document\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "Microsoft Edge": "tell application \"Microsoft Edge\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "Arc": "tell application \"Arc\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "Opera": "tell application \"Opera\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "Opera GX": "tell application \"Opera GX\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "시크릿 모드": "tell application \"시크릿 모드\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "네이버 웨일": "tell application \"네이버 웨일\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
        "Whale": "tell application \"Whale\"\nset t to title of active tab of window 1\nset u to URL of active tab of window 1\nreturn t & \"|TITLEURL|\" & u\nend tell",
    ]
}

// MARK: - AppDelegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    let workspace = NSWorkspace.shared
    var notificationObserver: NSObjectProtocol?
    var axObserver: NSObjectProtocol?

    // State
    var currentApp = "—"
    var currentPID: pid_t = 0
    var sessionStart = Date()
    var paused = false
    var totalTodaySeconds: Double = 0
    var windowTitle = ""
    var windowURL = ""
    var windowTitleTime: Date = .distantPast
    var cachedAppName = ""
    var serverOK = false

    // Menu items — force unwrap because setupMenu() runs before use
    var appMenuItem: NSMenuItem!
    var timeMenuItem: NSMenuItem!
    var statusMenuItem: NSMenuItem!
    var pauseMenuItem: NSMenuItem!

    // Timers
    var heartbeatTimer: Timer?
    var statsTimer: Timer?

    // Server
    var httpServer: HTTPServer?

    // AX dialog
    var axPromptShown = false

    // HTTP session (no cache for heartbeats)
    private lazy var httpSession: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 10
        return URLSession(configuration: config)
    }()

    let logger = Logger(subsystem: "com.jsk.mactimetracker", category: "app")

    // MARK: - Deinit

    deinit {
        heartbeatTimer?.invalidate()
        statsTimer?.invalidate()
        if let obs = notificationObserver {
            workspace.notificationCenter.removeObserver(obs)
        }
        if let obs = axObserver {
            workspace.notificationCenter.removeObserver(obs)
        }
    }

    // MARK: - Lifecycle

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            if #available(macOS 11.0, *) {
                button.image = NSImage(systemSymbolName: "clock", accessibilityDescription: "Timer")
            } else {
                button.title = "⏱"
            }
            button.action = #selector(toggleMenu)
        }
        setupMenu()
        startServer()
        observeAppSwitches()
        setCurrentApp()
        checkServer()
        startTimers()

        // AX check
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            self?.checkAccessibilityPermission()
        }
        axObserver = workspace.notificationCenter.addObserver(
            forName: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification,
            object: nil, queue: .main
        ) { [weak self] _ in
            self?.checkAccessibilityPermission()
        }
    }

    // MARK: - Menu

    let menu = NSMenu()

    func setupMenu() {
        menu.removeAllItems()

        appMenuItem = NSMenuItem(title: "📌 현재 앱: \(currentApp)", action: nil, keyEquivalent: "")
        appMenuItem.isEnabled = false
        menu.addItem(appMenuItem)

        timeMenuItem = NSMenuItem(title: "⏱ 오늘: 0m", action: nil, keyEquivalent: "")
        timeMenuItem.isEnabled = false
        menu.addItem(timeMenuItem)

        statusMenuItem = NSMenuItem(title: "● 시작 중...", action: nil, keyEquivalent: "")
        statusMenuItem.isEnabled = false
        menu.addItem(statusMenuItem)

        menu.addItem(NSMenuItem.separator())

        pauseMenuItem = NSMenuItem(title: "⏸ 일시정지", action: #selector(togglePause), keyEquivalent: "")
        menu.addItem(pauseMenuItem)

        menu.addItem(NSMenuItem(title: "📊 대시보드 열기", action: #selector(openDashboard), keyEquivalent: "d"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "✕ 종료", action: #selector(quitApp), keyEquivalent: "q"))
    }

    @objc func toggleMenu(_ sender: Any?) {
        statusItem.menu = menu
        statusItem.button?.performClick(nil)
        statusItem.menu = nil
    }

    // MARK: - Server

    func startServer() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            // Port 8000 충돌 체크
            let inUse = self.isPortInUse(8000)
            if inUse {
                logger.log("서버 이미 실행 중 (port 8000)")
                DispatchQueue.main.async {
                    self.serverOK = true
                    self.statusMenuItem.title = "● 실행중"
                }
                return
            }
            let server = HTTPServer(port: 8000)
            server.start()
            self.httpServer = server
            Thread.sleep(forTimeInterval: 0.3)
            DispatchQueue.main.async {
                self.serverOK = true
                self.statusMenuItem.title = "● 실행중"
                self.logger.log("HTTP 서버 시작됨 (port 8000)")
            }
        }
    }

    func stopServer() {
        httpServer?.stop()
        httpServer = nil
    }

    private func isPortInUse(_ port: UInt16) -> Bool {
        let sock = socket(AF_INET, SOCK_STREAM, 0)
        guard sock >= 0 else { return false }
        // SO_REUSEADDR로 TIME_WAIT 우회
        var reuse: Int32 = 1
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, socklen_t(MemoryLayout<Int32>.size))

        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = CFSwapInt16HostToBig(port)
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_addr.s_addr = INADDR_ANY  // 0.0.0.0

        let bindResult = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(sock, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        close(sock)
        return bindResult != 0  // bind failed = port in use
    }

    // MARK: - Accessibility

    func checkAccessibilityPermission() {
        if AXIsProcessTrusted() {
            logger.notice("✅ AX 권한 있음 (직접 AX API 사용)")
            return
        }
        let osaWorks = runViaOSA("tell application \"System Events\" to get name of every process")
        if !osaWorks.isEmpty {
            logger.notice("✅ AX 권한 없지만 osascript fallback 사용 가능")
            return
        }
        logger.warning("⚠️ AX 권한 없음 — 다이얼로그 표시 (1회만)")
        DispatchQueue.main.async { [weak self] in
            guard let self = self, !self.axPromptShown else { return }
            self.axPromptShown = true
            self.showAccessibilityPrompt()
        }
    }

    func showAccessibilityPrompt() {
        let alert = NSAlert()
        alert.messageText = "🔒 Accessibility 권한 필요"
        alert.informativeText = "Mac Time Tracker가 창 제목을 추적하려면 손쉬운 사용 권한이 필요합니다.\n\n"
            + "1. 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용\n"
            + "2. Mac Time Tracker.app 추가 (➕ 버튼)\n"
            + "3. 체크박스 활성화\n\n"
            + "권한 추가 후 Mac Time Tracker를 재시작하세요."
        alert.alertStyle = .informational
        alert.addButton(withTitle: "시스템 설정 열기")
        alert.addButton(withTitle: "나중에")
        let response = alert.runModal()
        if response == .alertFirstButtonReturn {
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
                NSWorkspace.shared.open(url)
            }
        }
    }

    // MARK: - App Switch Detection

    func observeAppSwitches() {
        notificationObserver = workspace.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: nil, queue: .main
        ) { [weak self] note in
            guard let self = self,
                  let app = note.userInfo?[NSWorkspace.applicationUserInfoKey]
                    as? NSRunningApplication,
                  let name = app.localizedName
            else { return }
            self.onAppChanged(name: name, pid: app.processIdentifier)
        }
    }

    func setCurrentApp() {
        if let app = workspace.frontmostApplication, let name = app.localizedName {
            currentApp = name
            currentPID = app.processIdentifier
            appMenuItem.title = "📌 현재 앱: \(name)"
        }
    }

    func onAppChanged(name: String, pid: pid_t) {
        guard !paused else { return }
        let now = Date()
        let duration = now.timeIntervalSince(sessionStart)
        sendHeartbeat(app: name, timestamp: now, duration: duration)
        currentApp = name
        currentPID = pid
        sessionStart = now
        appMenuItem.title = "📌 현재 앱: \(name)"
    }

    @objc func heartbeatTick() {
        guard !paused else { return }
        guard let app = workspace.frontmostApplication,
              let name = app.localizedName else { return }
        let now = Date()
        let duration = now.timeIntervalSince(sessionStart)
        sendHeartbeat(app: name, timestamp: now, duration: duration)
        sessionStart = now
        if name != currentApp {
            currentApp = name
            currentPID = app.processIdentifier
            appMenuItem.title = "📌 현재 앱: \(name)"
        }
    }

    func startTimers() {
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: Config.heartbeatInterval,
            repeats: true) { [weak self] _ in self?.heartbeatTick() }
        statsTimer = Timer.scheduledTimer(withTimeInterval: Config.statsRefreshInterval,
            repeats: true) { [weak self] _ in self?.checkServer() }
        Timer.scheduledTimer(withTimeInterval: 3, repeats: false) { [weak self] _ in
            self?.checkServer()
        }
    }

    // MARK: - Window Title

    func getWindowTitle() -> String {
        let now = Date()
        guard let app = workspace.frontmostApplication,
              let name = app.localizedName else {
            windowTitle = ""
            windowURL = ""
            cachedAppName = ""
            windowTitleTime = now
            return ""
        }

        // 캐시는 같은 앱에서만 유효 (앱 전환 시 무효화)
        if now.timeIntervalSince(windowTitleTime) < Config.windowTitleCacheTTL, cachedAppName == name {
            return windowTitle
        }

        var title = ""
        var url = ""

        // 1. CGWindow API (Core Graphics — instant, no permissions needed, works for all apps)
        title = cgWindowTitle(pid: app.processIdentifier)

        // 2. Browser AppleScript — only for URL capture + title fallback if CGWindow missed
        if let script = Config.browserScripts[name] {
            let output = runViaOSA(script)
            if let sepRange = output.range(of: "|TITLEURL|") {
                // AppleScript got both title and URL — use its title (more accurate for browser tabs)
                title = String(output[output.startIndex..<sepRange.lowerBound])
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                url = String(output[sepRange.upperBound...])
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            } else if title.isEmpty {
                // AppleScript failed or returned no separator, CGWindow also failed
                title = output
            }
            // else: CGWindow already has title, AppleScript failed — keep CGWindow title
        }

        // 3. Firefox special handling (no URL via AppleScript, CGWindow may miss it)
        if title.isEmpty, name == "Firefox" {
            title = runViaOSA("tell application \"System Events\" to tell process \"firefox\" to get title of window 1")
        }

        // 4. System Events via displayed name (handles localizedName != process name)
        if title.isEmpty {
            title = runViaOSA(
                "tell application \"System Events\" to tell (first process whose displayed name is \"\(name)\") to get title of window 1")
        }

        // 5. AX API as ultimate fallback (needs AX trust, usually not needed)
        if title.isEmpty {
            title = axWindowTitle(pid: app.processIdentifier)
        }

        windowTitle = title
        windowURL = url
        cachedAppName = name
        windowTitleTime = now
        return title
    }

    /// Get window title via Core Graphics Window Server API — no special permissions needed.
    private func cgWindowTitle(pid: pid_t) -> String {
        let option: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
        guard let windows = CGWindowListCopyWindowInfo(option, kCGNullWindowID) as? [[String: Any]] else {
            return ""
        }
        let intPid = Int(pid) // kCGWindowOwnerPID is CFNumber → Int in Swift, not Int32
        for w in windows {
            guard (w[kCGWindowLayer as String] as? Int) == 0 else { continue }
            guard let ownerPID = w[kCGWindowOwnerPID as String] as? Int,
                  ownerPID == intPid else { continue }
            if let name = w[kCGWindowName as String] as? String, !name.isEmpty {
                return name.trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return ""
    }

    func getFrontmostApp() -> String {
        guard let app = workspace.frontmostApplication,
              let name = app.localizedName else { return "" }
        return name
    }

    func runViaOSA(_ script: String) -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", script]
        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe
        do {
            try process.run()
            process.waitUntilExit()
            if process.terminationStatus != 0 {
                let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
                if let errStr = String(data: errData, encoding: .utf8), !errStr.isEmpty {
                    logger.error("osascript err: \(errStr)")
                }
                return ""
            }
            let data = outPipe.fileHandleForReading.readDataToEndOfFile()
            return String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        } catch {
            return ""
        }
    }

    func axWindowTitle(pid: pid_t) -> String {
        let appRef = AXUIElementCreateApplication(pid)
        var focused: CFTypeRef?
        let focusResult = AXUIElementCopyAttributeValue(
            appRef, kAXFocusedWindowAttribute as CFString, &focused)
        guard focusResult == .success else { return "" }

        // focusResult == .success guarantees correct type, forced cast is safe
        let winElement = focused as! AXUIElement
        var title: CFTypeRef?
        let titleResult = AXUIElementCopyAttributeValue(
            winElement, kAXTitleAttribute as CFString, &title)
        guard titleResult == .success, let str = title as? String else { return "" }
        return str.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - HTTP

    func sendHeartbeat(app: String, timestamp: Date, duration: TimeInterval) {
        let title = getWindowTitle()
        let finalTitle = title.isEmpty ? app : title
        var dataDict: [String: String] = ["app": app, "title": finalTitle]
        // URL은 브라우저 앱에서만 의미 있음
        // 캐시 히트로 이전 앱의 URL이 남아있는 경우 방지
        if !windowURL.isEmpty, Config.browserScripts.keys.contains(app) {
            dataDict["url"] = windowURL
        }
        let body: [String: Any] = [
            "timestamp": timestamp.timeIntervalSince1970,
            "duration": max(duration, 1.0),
            "data": dataDict
        ]
        guard let jsonData = try? JSONSerialization.data(withJSONObject: body),
              let url = URL(string: "\(Config.serverURL)/api/heartbeat") else { return }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = jsonData

        httpSession.dataTask(with: req) { data, resp, error in
            DispatchQueue.main.async { [weak self] in
                if let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 {
                    self?.serverOK = true
                } else if let error = error {
                    self?.logger.error("heartbeat 실패: \(error.localizedDescription)")
                }
            }
        }.resume()
    }

    func checkServer() {
        guard let url = URL(string: "\(Config.serverURL)/api/today") else { return }
        httpSession.dataTask(with: url) { [weak self] data, resp, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200,
                   let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let total = json["total_seconds"] as? Double {
                    self.serverOK = true
                    self.totalTodaySeconds = total
                    self.timeMenuItem.title = "⏱ 오늘: \(self.formatTime(total))"
                    self.statusMenuItem.title = "● 실행중"
                } else {
                    self.serverOK = false
                    self.statusMenuItem.title = "○ 서버 연결 끊김"
                    self.timeMenuItem.title = "⏱ 오늘: — (서버 꺼짐)"
                }
            }
        }.resume()
    }

    // MARK: - Actions

    @objc func togglePause(_ sender: NSMenuItem) {
        paused.toggle()
        if paused {
            sender.title = "▶ 재개"
            statusMenuItem.title = "⏸ 일시정지"
            appMenuItem.title = "📌 현재 앱: \(currentApp) (일시정지)"
        } else {
            sender.title = "⏸ 일시정지"
            statusMenuItem.title = "● 실행중"
            sessionStart = Date()
            appMenuItem.title = "📌 현재 앱: \(currentApp)"
            heartbeatTick()
        }
    }

    @objc func openDashboard(_ sender: Any?) {
        if let url = URL(string: "\(Config.serverURL)/") {
            NSWorkspace.shared.open(url)
        }
    }

    @objc func quitApp(_ sender: Any?) {
        stopServer()
        if let obs = notificationObserver {
            workspace.notificationCenter.removeObserver(obs)
        }
        if let obs = axObserver {
            workspace.notificationCenter.removeObserver(obs)
        }
        NSApplication.shared.terminate(nil)
    }

    // MARK: - Util

    func formatTime(_ seconds: Double) -> String {
        let s = Int(seconds)
        let h = s / 3600
        let m = (s % 3600) / 60
        let sec = s % 60
        if h > 0 { return "\(h)h \(String(format: "%02d", m))m" }
        return "\(m)m \(String(format: "%02d", sec))s"
    }
}
