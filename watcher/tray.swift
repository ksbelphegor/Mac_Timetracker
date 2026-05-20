import Cocoa
import Foundation

// MARK: - Configuration

enum Config {
    static let serverURL = "http://localhost:8000"
    static let heartbeatInterval: TimeInterval = 5
    static let statsRefreshInterval: TimeInterval = 60
    static let windowTitleCacheTTL: TimeInterval = 2
    static let serverStartRetries = 6
    static let serverRetryDelay: TimeInterval = 1.0

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

    /// Known-good Python paths (checked at startup for package availability)
    static let pythonCandidates = [
        "/Users/JSK/hermes-agent/venv/bin/python3",
        "/opt/homebrew/bin/python3",
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
    var serverStarting = false
    var resolvedPython: String?

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
        // 서버 시작을 비동기로 — 앱 시작 블로킹 금지
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.findPythonExecutable()
            self?.ensureServerRunning()
        }
        observeAppSwitches()
        setCurrentApp()
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

    // MARK: - Python / Server Management

    /// 올바른 Python 실행파일을 찾아 resolvedPython에 저장
    func findPythonExecutable() {
        // 이미 찾은 적 있으면 skip
        if resolvedPython != nil { return }

        for path in Config.pythonCandidates {
            guard FileManager.default.isExecutableFile(atPath: path) else { continue }
            // 필수 패키지 존재 여부 확인
            let check = Process()
            check.executableURL = URL(fileURLWithPath: path)
            check.arguments = ["-c", "import fastapi, uvicorn; print('ok')"]
            let pipe = Pipe()
            check.standardOutput = pipe
            check.standardError = pipe
            do {
                try check.run()
                check.waitUntilExit()
                if check.terminationStatus == 0 {
                    resolvedPython = path
                    print("✅ Python 발견: \(path)")
                    return
                }
            } catch {}
        }

        // Fallback: shell 환경에서 python3 찾기 (GUI 앱은 ~/.zshrc 안 읽음)
        let shell = Process()
        shell.executableURL = URL(fileURLWithPath: "/bin/zsh")
        shell.arguments = ["-lc", "which python3"]
        let pipe = Pipe()
        shell.standardOutput = pipe
        shell.standardError = FileHandle.nullDevice
        do {
            try shell.run()
            shell.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            if let path = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines),
               !path.isEmpty,
               FileManager.default.isExecutableFile(atPath: path) {
                resolvedPython = path
                print("✅ Python 발견 (shell): \(path)")
                return
            }
        } catch {}
        print("⚠️ Python을 찾을 수 없음 — 대시보드 서버 미실행")
    }

    /// 서버가 실행 중인지 확인하고, 없으면 시작
    func ensureServerRunning() {
        if checkServerRunning() { return }

        guard let python = resolvedPython else {
            DispatchQueue.main.async {
                self.statusMenuItem.title = "○ Python 없음"
            }
            return
        }

        startServerProcess(python: python)
        // 서버가 뜰 때까지 대기
        for _ in 0..<Config.serverStartRetries {
            Thread.sleep(forTimeInterval: Config.serverRetryDelay)
            if checkServerRunning() {
                DispatchQueue.main.async {
                    self.serverOK = true
                    self.statusMenuItem.title = "● 실행중"
                    self.updateTimeDisplay()
                }
                print("✅ 서버 시작 완료")
                return
            }
        }
        print("❌ 서버 시작 실패 (\(Config.serverStartRetries)회 시도)")
    }

    /// 단순 HTTP GET으로 서버 상태 확인
    func checkServerRunning() -> Bool {
        let semaphore = DispatchSemaphore(value: 0)
        var running = false
        guard let url = URL(string: "\(Config.serverURL)/api/today") else { return false }
        URLSession.shared.dataTask(with: url) { data, resp, error in
            if let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 {
                running = true
            }
            semaphore.signal()
        }.resume()
        _ = semaphore.wait(timeout: .now() + 3)
        return running
    }

    /// 서버 프로세스 실행 (dashboard/api.py)
    func startServerProcess(python: String) {
        stopServer()
        serverStarting = true

        let logPath = scriptDir + "/logs/api.log"
        let apiPath = scriptDir + "/dashboard/api.py"
        let dbDir = (scriptDir as NSString).appendingPathComponent(".mactimetracker")

        try? FileManager.default.createDirectory(atPath: scriptDir + "/logs",
            withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(atPath: dbDir,
            withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: logPath, contents: nil)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [apiPath]
        process.currentDirectoryURL = URL(fileURLWithPath: scriptDir)

        if let handle = FileHandle(forWritingAtPath: logPath) {
            process.standardOutput = handle
            process.standardError = handle
        }

        // PATH 환경변수 설정 (dashboard.py가 pip 패키지 찾게)
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = scriptDir + "/dashboard"
        process.environment = env

        do {
            try process.run()
            serverProcess = process
            print("서버 시작 시도 (Python: \(python), PID: \(process.processIdentifier))")
        } catch {
            print("서버 시작 실패: \(error.localizedDescription)")
        }
        serverStarting = false
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
        // 서버가 아직 안 떴으면 10초 후 재시도
        Timer.scheduledTimer(withTimeInterval: 10, repeats: false) { [weak self] _ in
            guard let self = self, !self.serverOK else { return }
            DispatchQueue.global(qos: .userInitiated).async {
                self.ensureServerRunning()
            }
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
                    // 서버가 죽었으면 다시 시작 시도 (background)
                    if !self.serverStarting {
                        DispatchQueue.global(qos: .userInitiated).async {
                            self.ensureServerRunning()
                        }
                    }
                }
            }
        }.resume()
    }

    func updateTimeDisplay() {
        guard let url = URL(string: "\(Config.serverURL)/api/today") else { return }
        URLSession.shared.dataTask(with: url) { [weak self] data, resp, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let total = json["total_seconds"] as? Double {
                    self.totalTodaySeconds = total
                    self.timeMenuItem.title = "⏱ 오늘: \(self.formatTime(total))"
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
