#!/usr/bin/env python3
"""
창 제목 테스트 스크립트
"""
import sys
import os

# 현재 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from src.core.window_title_manager import get_window_title_manager
from AppKit import NSWorkspace
import time

def test_window_title():
    print("=== 창 제목 테스트 시작 ===")
    
    # 윈도우 제목 관리자 초기화
    window_manager = get_window_title_manager()
    
    for i in range(10):  # 10초 동안 테스트
        print(f"\n--- 테스트 {i+1} ---")
        
        # 현재 활성 앱 정보 가져오기
        try:
            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()
            
            if active_app:
                app_name = active_app['NSApplicationName']
                app_pid = active_app['NSApplicationProcessIdentifier']
                
                print(f"활성 앱: {app_name} (PID: {app_pid})")
                
                # 윈도우 제목 관리자를 통해 창 제목 가져오기
                active_window_info = window_manager.get_active_window_info()
                if active_window_info:
                    print(f"활성 창 정보: 앱={active_window_info[0]}, 제목={active_window_info[1]}")
                
                # 직접 창 제목 가져오기
                _, window_title = window_manager.get_window_title(app_name, app_pid)
                print(f"창 제목: {window_title}")
                
                # 강제 새로고침으로 창 제목 가져오기
                _, forced_title = window_manager.get_window_title(app_name, app_pid, force_refresh=True)
                print(f"강제 새로고침 창 제목: {forced_title}")
                
            else:
                print("활성 앱을 찾을 수 없습니다.")
                
        except Exception as e:
            print(f"오류 발생: {e}")
            import traceback
            traceback.print_exc()
        
        time.sleep(1)
    
    print("\n=== 창 제목 테스트 완료 ===")

if __name__ == "__main__":
    test_window_title()