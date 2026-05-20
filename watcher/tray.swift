import Cocoa
import Foundation

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

@main
class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    let workspace = NSWorkspace.shared
    var notificationObserver: NSObjectProtocol?

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

    // Server process
    var serverProcess: Process?

    var scriptDir: String {
        let bin = (#file as NSString).deletingLastPathComponent
        return (bin as NSString).deletingLastPathComponent  // watcher/ -> project root
    }

    // MARK: - Lifecycle

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "⏱"
            button.action = #selector(toggleMenu)
        }
        setupMenu()
        startServer()
        observeAppSwitches()
        setCurrentApp()
        checkServer()
        startTimers()
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

        statusMenuItem = NSMenuItem(title: "● 실행중", action: nil, keyEquivalent: "")
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

    // MARK: - Server Management

    func startServer() {
        stopServer()
        let logPath = scriptDir + "/logs/api.log"
        let apiPath = scriptDir + "/dashboard/api.py"

        // Ensure logs dir exists
        try? FileManager.default.createDirectory(atPath: scriptDir + "/logs",
            withIntermediateDirectories: true)

        // Create log file
        FileManager.default.createFile(atPath: logPath, contents: nil)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", apiPath]

        if let handle = FileHandle(forWritingAtPath: logPath) {
            process.standardOutput = handle
            process.standardError = handle
        }

        do {
            try process.run()
            serverProcess = process
        } catch {
            print("Server start failed: \(error)")
        }
    }

    func stopServer() {
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
            serverProcess = nil
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
        let appName = getFrontmostApp()

        if let script = Config.browserScripts[appName] {
            title = runAppleScript(script)
        }
        if title.isEmpty {
            title = axWindowTitle(appName: appName)
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

    func runAppleScript(_ script: String) -> String {
        guard let scriptObj = NSAppleScript(source: script) else { return "" }
        var error: NSDictionary?
        let result = scriptObj.executeAndReturnError(&error)
        if error == nil, let str = result.stringValue {
            return str.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return ""
    }

    func axWindowTitle(appName: String) -> String {
        guard !appName.isEmpty else { return "" }
        return runAppleScript(
            "tell application \"System Events\" to tell process \"\(appName)\" to get title of window 1")
    }

    // MARK: - HTTP

    func sendHeartbeat(app: String, timestamp: Date, duration: TimeInterval) {
        let title = getWindowTitle()
        let body: [String: Any] = [
            "timestamp": timestamp.timeIntervalSince1970,
            "duration": max(duration, 1.0),
            "data": ["app": app, "title": title.isEmpty ? app : title]
        ]
        guard let jsonData = try? JSONSerialization.data(withJSONObject: body),
              let url = URL(string: "\(Config.serverURL)/api/heartbeat") else { return }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = jsonData

        URLSession.shared.dataTask(with: req) { [weak self] data, resp, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 {
                    self.serverOK = true
                    self.statusMenuItem.title = "● 실행중"
                } else {
                    self.statusMenuItem.title = error == nil ? "● 실행중" : "○ 서버 연결 끊김"
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
