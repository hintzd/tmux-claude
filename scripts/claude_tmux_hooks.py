#!/usr/bin/env python3

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from debug_logger import DebugLogger

logger = DebugLogger('claude_tmux_hooks')

STATUS_EMOJIS = {
    'running': '🏃',
    'stop': '✅',
    'permission': '❓',
}
KNOWN_PREFIXES = tuple(f"{emoji} " for emoji in STATUS_EMOJIS.values())


def get_script_dir():
    return Path(__file__).parent


def get_current_tmux_pane():
    logger.log_function_call('get_current_tmux_pane')
    try:
        cmd = ['tmux', 'display-message', '-p', '#{pane_id}']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        pane_id = result.stdout.strip()
        logger.log_tmux_command(cmd, pane_id)
        return pane_id
    except subprocess.CalledProcessError as e:
        logger.log_tmux_command(['tmux', 'display-message', '-p', '#{pane_id}'], error=str(e))
        logger.error(f"Failed to get current pane ID: {e}")
        return None


def get_current_tmux_session():
    logger.log_function_call('get_current_tmux_session')
    try:
        cmd = ['tmux', 'display-message', '-p', '#{session_name}']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        session_name = result.stdout.strip()
        logger.log_tmux_command(cmd, session_name)
        return session_name
    except subprocess.CalledProcessError as e:
        logger.log_tmux_command(['tmux', 'display-message', '-p', '#{session_name}'], error=str(e))
        logger.error(f"Failed to get current session: {e}")
        return None


def get_pane_name(pane_id):
    logger.log_function_call('get_pane_name', args=[pane_id])
    try:
        cmd = ['tmux', 'display-message', '-p', '-t', pane_id, '#{window_name}']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        pane_name = result.stdout.strip()
        logger.log_tmux_command(cmd, pane_name)
        return pane_name
    except subprocess.CalledProcessError as e:
        logger.log_tmux_command(['tmux', 'display-message', '-p', '-t', pane_id, '#{window_name}'], error=str(e))
        logger.error(f"Failed to get window name for {pane_id}: {e}")
        return None


def get_window_auto_rename_status(pane_id):
    logger.log_function_call('get_window_auto_rename_status', args=[pane_id])
    try:
        cmd = ['tmux', 'show-options', '-t', pane_id, 'automatic-rename']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        logger.log_tmux_command(cmd, output)
        return 'on' in output
    except subprocess.CalledProcessError as e:
        logger.log_tmux_command(['tmux', 'show-options', '-t', pane_id, 'automatic-rename'], error=str(e))
        logger.debug(f"Could not get automatic-rename status for {pane_id}, assuming off")
        return False


def set_window_auto_rename(pane_id, enabled):
    logger.log_function_call('set_window_auto_rename', args=[pane_id, enabled])
    value = 'on' if enabled else 'off'
    try:
        cmd = ['tmux', 'set-option', '-t', pane_id, 'automatic-rename', value]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.log_tmux_command(cmd, "SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        logger.log_tmux_command(['tmux', 'set-option', '-t', pane_id, 'automatic-rename', value], error=str(e))
        logger.error(f"Failed to set automatic-rename for {pane_id}: {e}")
        return False


def set_pane_name(pane_id, name):
    logger.log_function_call('set_pane_name', args=[pane_id, name])
    try:
        set_window_auto_rename(pane_id, False)
        cmd = ['tmux', 'rename-window', '-t', pane_id, name]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.log_tmux_command(cmd, "SUCCESS")
        logger.info(f"Set pane {pane_id} window name to: {name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.log_tmux_command(['tmux', 'rename-window', '-t', pane_id, name], error=str(e))
        logger.error(f"Failed to set window name for {pane_id}: {e}")
        return False


def get_state_file(pane_id):
    return get_script_dir() / f".pane_state_{pane_id.replace('%', '')}.json"


def save_pane_state(pane_id, original_name, status):
    logger.log_function_call('save_pane_state', args=[pane_id, original_name, status])
    auto_rename_was_on = get_window_auto_rename_status(pane_id)
    state = {
        'pane_id': pane_id,
        'original_name': original_name,
        'status': status,
        'timestamp': time.time(),
        'auto_rename_was_on': auto_rename_was_on,
    }
    try:
        with open(get_state_file(pane_id), 'w') as f:
            json.dump(state, f)
        logger.log_pane_state(pane_id, f"SAVED_{status.upper()}", state)
        logger.info(f"Saved state for pane {pane_id}: {status}")
    except IOError as e:
        logger.error(f"Failed to save state for pane {pane_id}: {e}")


def load_pane_state(pane_id):
    logger.log_function_call('load_pane_state', args=[pane_id])
    state_file = get_state_file(pane_id)
    if not state_file.exists():
        logger.debug(f"No state file found for pane {pane_id}")
        return None
    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
        logger.log_pane_state(pane_id, "LOADED", state)
        return state
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load state for pane {pane_id}: {e}")
        return None


def cleanup_pane_state(pane_id):
    logger.log_function_call('cleanup_pane_state', args=[pane_id])
    state_file = get_state_file(pane_id)
    if not state_file.exists():
        logger.debug(f"No state file to cleanup for pane {pane_id}")
        return
    try:
        state_file.unlink()
        logger.log_pane_state(pane_id, "CLEANED_UP")
        logger.info(f"Cleaned up state for pane {pane_id}")
    except OSError as e:
        logger.error(f"Failed to cleanup state for pane {pane_id}: {e}")


def strip_status_prefix(name):
    for prefix in KNOWN_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def get_claude_pane_id():
    logger.log_function_call('get_claude_pane_id')
    pane_id = os.environ.get('TMUX_PANE')
    if pane_id:
        logger.debug(f"Got pane ID from TMUX_PANE: {pane_id}")
        return pane_id
    pane_id = get_current_tmux_pane()
    if pane_id:
        logger.debug(f"Using current pane ID as fallback: {pane_id}")
        return pane_id
    logger.error("Could not determine Claude pane ID")
    return None


def set_status_for_pane(pane_id, status):
    logger.log_function_call('set_status_for_pane', args=[pane_id, status])
    current_name = get_pane_name(pane_id)
    if not current_name:
        logger.error(f"Could not get current name for pane {pane_id}")
        return False
    state = load_pane_state(pane_id)
    original_name = state['original_name'] if state else strip_status_prefix(current_name)
    new_name = f"{STATUS_EMOJIS[status]} {original_name}"
    if not set_pane_name(pane_id, new_name):
        logger.error(f"Failed to set pane name for {pane_id}")
        return False
    save_pane_state(pane_id, original_name, status)
    return True


def handle_running_hook():
    logger.log_function_call('handle_running_hook')
    logger.info("Processing Claude running hook")
    pane_id = get_claude_pane_id()
    if not pane_id:
        logger.error("Could not get Claude pane ID")
        logger.log_hook_execution('RUNNING', None, success=False)
        return
    success = set_status_for_pane(pane_id, 'running')
    logger.log_hook_execution('RUNNING', pane_id, success=success)


def handle_stop_hook():
    logger.log_function_call('handle_stop_hook')
    logger.info("Processing Claude stop hook")
    pane_id = get_claude_pane_id()
    if not pane_id:
        logger.error("Could not get Claude pane ID")
        logger.log_hook_execution('STOP', None, success=False)
        return
    success = set_status_for_pane(pane_id, 'stop')
    logger.log_hook_execution('STOP', pane_id, success=success)


def handle_permission_hook():
    logger.log_function_call('handle_permission_hook')
    logger.info("Processing Claude permission hook")
    pane_id = get_claude_pane_id()
    if not pane_id:
        logger.error("Could not get Claude pane ID")
        logger.log_hook_execution('PERMISSION', None, success=False)
        return
    success = set_status_for_pane(pane_id, 'permission')
    logger.log_hook_execution('PERMISSION', pane_id, success=success)


def restore_pane_name(pane_id):
    logger.log_function_call('restore_pane_name', args=[pane_id])
    logger.info(f"Restoring original name for pane {pane_id}")
    state = load_pane_state(pane_id)
    if not state:
        logger.warning(f"No state found for pane {pane_id} to restore")
        return False
    original_name = state['original_name']
    auto_rename_was_on = state.get('auto_rename_was_on', True)
    try:
        cmd = ['tmux', 'rename-window', '-t', pane_id, original_name]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.log_tmux_command(cmd, "SUCCESS")
        logger.info(f"Restored pane {pane_id} window name to: {original_name}")
        set_window_auto_rename(pane_id, auto_rename_was_on)
        cleanup_pane_state(pane_id)
        return True
    except subprocess.CalledProcessError as e:
        logger.log_tmux_command(['tmux', 'rename-window', '-t', pane_id, original_name], error=str(e))
        logger.error(f"Failed to restore pane {pane_id} name: {e}")
        return False


def clear_emoji_on_enter():
    logger.log_function_call('clear_emoji_on_enter')
    pane_id = get_current_tmux_pane()
    if not pane_id:
        return
    if load_pane_state(pane_id):
        restore_pane_name(pane_id)


def main():
    if len(sys.argv) < 2:
        print("Usage: claude_tmux_hooks.py [running|stop|permission|restore|clear_emoji_on_enter] [pane_id]")
        sys.exit(1)

    action = sys.argv[1]
    logger.info(f"Starting claude_tmux_hooks with action: {action}")

    try:
        if action == 'running':
            handle_running_hook()
        elif action == 'stop':
            handle_stop_hook()
        elif action == 'permission':
            handle_permission_hook()
        elif action == 'restore':
            pane_id = sys.argv[2] if len(sys.argv) >= 3 else get_claude_pane_id()
            if pane_id:
                restore_pane_name(pane_id)
            else:
                logger.error("Could not get Claude pane ID for restore")
        elif action == 'clear_emoji_on_enter':
            clear_emoji_on_enter()
        else:
            logger.error(f"Unknown action: {action}")
            print(f"Unknown action: {action}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        raise


if __name__ == '__main__':
    main()
