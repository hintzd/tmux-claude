#!/usr/bin/env python3

import subprocess
import json
from pathlib import Path
from typing import Dict, Optional, List
from debug_logger import DebugLogger

SHARED_TRACKER = Path.home() / '.config' / 'tmux' / 'ai-pane-tracker.json'

class TmuxIntegration:
    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.logger = DebugLogger('tmux_integration')

    def run_tmux_command(self, args: List[str]) -> Optional[str]:
        self.logger.log_function_call('run_tmux_command', args=[args])
        try:
            cmd = ['tmux'] + args
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            self.logger.log_tmux_command(cmd, output)
            return output
        except subprocess.CalledProcessError as e:
            self.logger.log_tmux_command(['tmux'] + args, error=str(e))
            self.logger.error(f"Tmux command failed: {e}")
            return None

    def get_all_panes(self) -> List[Dict]:
        panes = []
        output = self.run_tmux_command([
            'list-panes', '-a', '-F',
            '#{session_name}\t#{window_index}\t#{pane_index}\t#{window_name}\t#{pane_id}\t#{pane_title}\t#{pane_pid}',
        ])
        if output:
            for line in output.split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) == 7:
                        panes.append({
                            'session_name': parts[0],
                            'window_index': parts[1],
                            'pane_index': parts[2],
                            'window_name': parts[3],
                            'pane_id': parts[4],
                            'title': parts[5],
                            'pid': parts[6],
                        })
        return panes

    def get_pane_info(self, pane_id: str) -> Optional[Dict]:
        output = self.run_tmux_command([
            'display-message', '-p', '-t', pane_id,
            '#{session_name}\t#{window_index}\t#{pane_index}\t#{window_name}\t#{pane_id}\t#{pane_title}\t#{pane_pid}',
        ])
        if output:
            parts = output.split('\t')
            if len(parts) == 7:
                return {
                    'session_name': parts[0],
                    'window_index': parts[1],
                    'pane_index': parts[2],
                    'window_name': parts[3],
                    'pane_id': parts[4],
                    'title': parts[5],
                    'pid': parts[6],
                }
        return None

    def get_pane_title(self, pane_id: str) -> Optional[str]:
        return self.run_tmux_command(['display-message', '-p', '-t', pane_id, '#{window_name}'])

    def set_pane_title(self, pane_id: str, title: str) -> bool:
        try:
            subprocess.run(['tmux', 'rename-window', '-t', pane_id, title],
                           check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def get_current_pane(self) -> Optional[str]:
        return self.run_tmux_command(['display-message', '-p', '#{pane_id}'])

    def get_current_session(self) -> Optional[str]:
        return self.run_tmux_command(['display-message', '-p', '#{session_name}'])

    def get_all_sessions(self) -> List[str]:
        output = self.run_tmux_command(['list-sessions', '-F', '#{session_name}'])
        if not output:
            return []
        return [line for line in output.split('\n') if line.strip()]

    def is_pane_active(self, pane_id: str) -> bool:
        return self.get_current_pane() == pane_id

    # --- Shared AI pane tracker ---

    def load_tracked_panes(self) -> Dict:
        """Load AI agent panes from the shared tracker file."""
        if not SHARED_TRACKER.exists():
            return {}
        try:
            with open(SHARED_TRACKER, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save_tracked_panes(self, tracked_panes: Dict):
        """Persist AI agent panes to the shared tracker file."""
        SHARED_TRACKER.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(SHARED_TRACKER, 'w') as f:
                json.dump(tracked_panes, f, indent=2)
        except OSError:
            pass

    def register_ai_pane(self, pane_id: str, agent: str) -> bool:
        """Track a pane as an AI agent pane (agent = 'claude' or 'codex')."""
        pane_info = self.get_pane_info(pane_id)
        if not pane_info:
            return False
        tracked = self.load_tracked_panes()
        tracked[pane_id] = {
            'agent': agent,
            'session_name': pane_info['session_name'],
        }
        self.save_tracked_panes(tracked)
        return True

    def unregister_ai_pane(self, pane_id: str):
        """Remove a pane from the shared tracker."""
        tracked = self.load_tracked_panes()
        if pane_id in tracked:
            del tracked[pane_id]
            self.save_tracked_panes(tracked)

    def set_session_marker(self, session_name: str, marker: str) -> bool:
        """Set the picker marker for a tmux session."""
        try:
            subprocess.run(
                ['tmux', 'set-option', '-t', session_name, '@ai_session_marker', marker],
                check=True, capture_output=True, text=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def refresh_session_markers(self):
        """Refresh the 🤖 count marker for every tmux session."""
        tracked = self.load_tracked_panes()
        current_pane_ids = {pane['pane_id'] for pane in self.get_all_panes()}

        session_counts: Dict[str, int] = {}
        for pane_id, info in tracked.items():
            if pane_id in current_pane_ids:
                s = info.get('session_name', '')
                if s:
                    session_counts[s] = session_counts.get(s, 0) + 1

        for session_name in self.get_all_sessions():
            count = session_counts.get(session_name, 0)
            marker = '🤖' * count + (' ' if count > 0 else '')
            self.set_session_marker(session_name, marker)

    # --- Cleanup ---

    def cleanup_dead_panes(self):
        """Clean up state files for panes that no longer exist."""
        current_panes = {pane['pane_id'] for pane in self.get_all_panes()}
        for state_file in self.script_dir.glob('.pane_state_*.json'):
            try:
                pane_id = '%' + state_file.stem.replace('.pane_state_', '')
                if pane_id not in current_panes:
                    state_file.unlink()
            except Exception:
                pass


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: tmux_integration.py [command] [args...]")
        sys.exit(1)

    tmux = TmuxIntegration()
    command = sys.argv[1]

    if command == 'list-panes':
        for pane in tmux.get_all_panes():
            print(f"{pane['pane_id']}: {pane['title']} (PID: {pane['pid']})")

    elif command == 'find-claude':
        # kept for debugging; lists panes from shared tracker with agent=claude
        tracked = tmux.load_tracked_panes()
        for pane_id, info in tracked.items():
            if info.get('agent') == 'claude':
                print(f"{pane_id}: session={info.get('session_name')}")

    elif command == 'refresh-session-markers':
        tmux.refresh_session_markers()

    elif command == 'get-title':
        if len(sys.argv) >= 3:
            title = tmux.get_pane_title(sys.argv[2])
            if title:
                print(title)

    elif command == 'set-title':
        if len(sys.argv) >= 4:
            success = tmux.set_pane_title(sys.argv[2], sys.argv[3])
            print("OK" if success else "FAILED")

    elif command == 'current-pane':
        pane_id = tmux.get_current_pane()
        if pane_id:
            print(pane_id)

    elif command == 'cleanup':
        tmux.cleanup_dead_panes()
        print("Cleanup completed")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
