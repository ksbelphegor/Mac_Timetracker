import Cocoa
import Foundation
import ApplicationServices

// MARK: - Configuration

enum Config {
    static let serverURL = "http://localhost:8000"
    static let heartbeatInterval: TimeInterval = 5
    static let statsRefreshInterval: TimeInterval = 60
    static let windowTitleCacheTTL: TimeInterval = 2

    static let browserScripts: [String: String] = [
        "Brave Browser": "tell application \"Brave Browser\" to get title of active tab of window 1",
        "Google Chrome": "tell application \"Google Chrome\" to get title of active tab of window 1",
        "Safari": "tell application \"Safari\" to get name of front document",
        "Firefox": "tell application \"System Events\" to tell process \"firefox\" to get title of window 1",
        "Microsoft Edge": "tell application \"Microsoft Edge\" to get title of active tab of window 1",
        "Arc": "tell application \"Arc\" to get title of active tab of window 1",
        "Opera": "tell application \"Opera\" to get title of active tab of window 1",
        "Opera GX": "tell application \"Opera GX\" to get title of active tab of window 1",
        "Orion": "tell application \"Orion\" to get title of active tab of window 1",
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
    var windowTitleTime: Date = .distantPast
    var serverOK = false

    // Menu items
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

    func setupMenu() {
        menu = NSMenu()

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

    var menu: NSMenu!

    @objc func toggleMenu(_ sender: Any?) {
        statusItem.menu = menu
        statusItem.button?.performClick(nil)
        statusItem.menu = nil
    }

    // MARK: - Server

    func startServer() {
        try? "startServer() called at \(Date())\n".write(toFile: "/tmp/mactt_debug.log", atomically: true, encoding: .utf8)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else {
                try? "startServer: self is nil!\n".write(toFile: "/tmp/mactt_debug.log", atomically: true, encoding: .utf8)
                return
            }
            // Port 8000 충돌 체크
            let inUse = self.isPortInUse(8000)
            try? "Port 8000 in use: \(inUse)\n".write(toFile: "/tmp/mactt_debug.log", atomically: true, encoding: .utf8)
            if inUse {
                print("서버 이미 실행 중 (port 8000)")
                DispatchQueue.main.async {
                    self.serverOK = true
                    self.statusMenuItem.title = "● 실행중"
                }
                return
            }
            let server = HTTPServer(port: 8000)
            try? "Starting server...\n".write(toFile: "/tmp/mactt_debug.log", atomically: true, encoding: .utf8)
            server.start()
            self.httpServer = server
            try? "Server started, waiting 0.3s...\n".write(toFile: "/tmp/mactt_debug.log", atomically: true, encoding: .utf8)
            Thread.sleep(forTimeInterval: 0.3)
            DispatchQueue.main.async {
                self.serverOK = true
                self.statusMenuItem.title = "● 실행중"
                print("HTTP 서버 시작됨 (port 8000)")
                try? "HTTP server running on :8000\n".write(toFile: "/tmp/mactt_debug.log", atomically: true, encoding: .utf8)
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
            print("✅ AX 권한 있음 (직접 AX API 사용)")
            return
        }
        let osaWorks = runViaOSA("tell application \"System Events\" to get name of every process")
        if !osaWorks.isEmpty {
            print("✅ AX 권한 없지만 osascript fallback 사용 가능")
            return
        }
        print("⚠️ AX 권한 없음 — 다이얼로그 표시 (1회만)")
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
        if now.timeIntervalSince(windowTitleTime) < Config.windowTitleCacheTTL {
            return windowTitle
        }

        var title = ""
        guard let app = workspace.frontmostApplication,
              let name = app.localizedName else {
            windowTitle = ""
            windowTitleTime = now
            return ""
        }

        // 1. Browser AppleScript (osascript subprocess)
        if let script = Config.browserScripts[name] {
            title = runViaOSA(script)
        }

        // 2. System Events (osascript subprocess, all apps)
        if title.isEmpty {
            title = runViaOSA(
                "tell application \"System Events\" to tell process \"\(name)\" to get title of window 1")
        }

        // 3. AX API (only if MacTT has direct AX trust)
        if title.isEmpty && AXIsProcessTrusted() {
            title = axWindowTitle(pid: app.processIdentifier)
        }

        windowTitle = title
        windowTitleTime = now
        return title
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
                    print("osascript err: \(errStr)")
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
        let body: [String: Any] = [
            "timestamp": timestamp.timeIntervalSince1970,
            "duration": max(duration, 1.0),
            "data": ["app": app, "title": finalTitle]
        ]
        guard let jsonData = try? JSONSerialization.data(withJSONObject: body),
              let url = URL(string: "\(Config.serverURL)/api/heartbeat") else { return }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = jsonData

        URLSession.shared.dataTask(with: req) { data, resp, error in
            if let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 {
                DispatchQueue.main.async { [weak self] in
                    self?.serverOK = true
                }
            }
        }.resume()
    }

    func checkServer() {
        guard let url = URL(string: "\(Config.serverURL)/api/today") else { return }
        URLSession.shared.dataTask(with: url) { [weak self] data, resp, error in
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
