"""Local, bounded native team-read requests. No Codex/image generation happens here."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import uuid

from live_refresh import write_json

PROFILE = 'fm27-steam-26620374-teams-v1'
VERSION = '0.4.2'


from squad_types import GameWait, TeamReadPending, snapshot_key


def root_path():
    if os.name != 'nt' or not os.environ.get('LOCALAPPDATA'):
        return None
    return Path(os.environ['LOCALAPPDATA'])/'FMFaceAutomator'/'team-reader'


def read(file):
    if file.stat().st_size > 256*1024:
        raise ValueError('팀 조회 파일 크기 초과')
    return json.loads(file.read_text(encoding='utf-8-sig'))


def connection(root, now, require_idle=True):
    found = []
    stale = False
    for file in sorted((root/'sessions').glob('*/status.json'))[-64:]:
        try:
            value = read(file)
            sid, pid = value['session'], value['pid']
            if (value.get('protocol') == 1 and value.get('profile') == PROFILE and value.get('plugin_version') in ('0.4.0', '0.4.1', VERSION)
                    and isinstance(sid,str) and re.fullmatch('[a-f0-9]{32}',sid) and type(pid) is int and pid > 0
                    and file.parent.name == f'{pid}-{sid}' and type(value.get('epoch')) is int):
                age = now - float(value['heartbeat'])
                if 0 <= age <= 5:
                    found.append((file.parent,value))
                elif age > 5 and value.get('reason') != 'cleanup_failed_restart_required':
                    stale = True
        except (OSError,ValueError,KeyError,TypeError):
            continue
    if len(found) != 1:
        if not found and stale:
            raise GameWait('게임 연결 응답 대기 · 게임이 응답하면 자동으로 재개합니다.')
        raise TeamReadPending('팀 구분 연결 대기 · FM27 종료 후 install_team_bindings.bat로 설치하고 연결한 세이브를 불러오세요.' if not found else 'FM27을 하나만 실행하세요.')
    directory, status = found[0]
    if status.get('reason') == 'cleanup_failed_restart_required':
        raise TeamReadPending('팀 조회 정리 오류 · 게임을 재시작한 뒤 다시 시도하세요.')
    if status.get('available') is not True:
        raise TeamReadPending('팀 조회 연결을 확인하세요.')
    if require_idle and (status.get('idle') is not True or status.get('binding_ready') is not True):
        raise GameWait('게임의 진행/저장이 끝나고 세이브가 열리면 자동으로 재개합니다.')
    return directory,status


class TeamReader:
    def __init__(self, root=None, clock=time.time, sleep=time.sleep):
        self.root = Path(root) if root is not None else root_path()
        self.clock, self.sleep = clock,sleep
        self.cache = {}
        self.last_context = None

    @staticmethod
    def classification_context(status):
        # Older DLLs invalidate on every busy epoch, preserving their strict behavior.
        context = status.get('context_epoch')
        return {'session': status['session'], 'human_team_index': status.get('human_team_index'),
                'generation': context if type(context) is int else status['epoch'],
                'kind': 'context' if type(context) is int else 'query'}

    def current_context(self):
        if self.root is None:
            return None
        _, status = connection(self.root, self.clock(), require_idle=False)
        return self.classification_context(status)

    def resolve(self, indexes, managed, snapshot, cancel=None):
        self.last_context = None
        if self.root is None:
            raise TeamReadPending('팀 구분 연결 대기 · Windows FM27에서 팀 조회 플러그인을 실행하세요.')
        directory,status = connection(self.root,self.clock())
        session,epoch = status['session'],status['epoch']
        human = status.get('human_team_index')
        managed = set(map(str,managed))
        if managed and (type(human) is not int or human < 0):
            raise GameWait('담당 구단 확인 대기 · 실행 중인 게임에서 연결한 세이브를 불러오세요.')
        targets = list(dict.fromkeys(([human] if managed else []) + list(indexes)))
        if any(type(i) is not int or i < 0 or i > 2147483647 for i in targets):
            raise TeamReadPending('등록 팀 인덱스 확인 불가')
        missing = [i for i in targets if (session,epoch,snapshot,i) not in self.cache]
        for offset in range(0,len(missing),4):
            batch = missing[offset:offset+4]
            result = self.request(directory,status,batch,snapshot,cancel)
            for row in result:
                self.cache[(session,epoch,snapshot,row['native_team_index'])] = row
            if len(self.cache) > 2048:
                keep = {key:self.cache[key] for key in self.cache if key[:3] == (session,epoch,snapshot)}
                required = {key:keep[key] for key in keep if key[3] in targets}
                self.cache = dict(list(keep.items())[-1024:]) | required
        _,fresh = connection(self.root,self.clock())
        if (fresh['session'],fresh['epoch']) != (session,epoch):
            raise GameWait('게임 상태가 변경되어 팀 구분을 다시 확인합니다.')
        if self.classification_context(fresh) != self.classification_context(status):
            raise GameWait('불러온 게임이 변경되어 팀 구분을 다시 확인합니다.')
        if managed:
            proof = self.cache.get((session,epoch,snapshot,human),{})
            club = (proof.get('values',{}).get('Club.UniqueId') or {})
            if club.get('error') or type(club.get('scalar')) is not int or str(club['scalar']) not in managed:
                raise TeamReadPending('연결한 세이브와 실행 중인 게임의 담당 구단이 다릅니다.')
        self.last_context = self.classification_context(fresh)
        return {i:self.cache[(session,epoch,snapshot,i)] for i in indexes}

    def request(self, directory, status, indexes, snapshot, cancel):
        now = self.clock(); identifier = uuid.uuid4().hex
        request = self.root/'requests'/status['session']/(identifier+'.json')
        response = directory/'responses'/(identifier+'.json')
        data = dict(protocol=1,id=identifier,session=status['session'],profile=PROFILE,epoch=status['epoch'],snapshot=snapshot,
                    teams=indexes,created_at=now,expires_at=now+40)
        write_json(request,data)
        try:
            while self.clock()-now < 42:
                if cancel is not None and cancel.is_set():
                    raise TeamReadPending('사용자 중단 · 팀 구분 조회 대기')
                if response.is_file():
                    result = read(response)
                    if any(result.get(k) != data[k] for k in ('protocol','id','session','profile','epoch','snapshot')):
                        raise TeamReadPending('팀 조회 응답의 세션/스냅샷이 다릅니다.')
                    rows = result.get('results')
                    if result.get('status') == 'unavailable' and isinstance(rows, list):
                        _, fresh = connection(self.root, self.clock())
                        transient = ('game_became_busy', 'request_expired_cancelled_or_game_changed', 'team_query_timeout')
                        if (fresh['session'], fresh['epoch']) != (status['session'], status['epoch']) or (
                                not rows or all(isinstance(row, dict) and not row.get('cleanup_error') and
                                (not row.get('error') or any(reason in row['error'] for reason in transient)) for row in rows)):
                            raise GameWait('게임 상태가 변경되어 팀 조회를 다시 준비합니다.')
                    if (result.get('status') != 'complete' or not isinstance(rows,list) or len(rows) != len(indexes)
                            or any(not isinstance(r,dict) or type(r.get('native_team_index')) is not int for r in rows)
                            or {r['native_team_index'] for r in rows} != set(indexes)
                            or any(r.get('error') or r.get('cleanup_error') for r in rows)):
                        raise TeamReadPending('팀 구분 조회 미완료 · 게임이 안정되면 자동으로 재시도합니다.')
                    return rows
                _, fresh = connection(self.root,self.clock())
                if (fresh['session'],fresh['epoch']) != (status['session'],status['epoch']):
                    raise GameWait('게임 세션이 변경되어 팀 구분을 다시 확인합니다.')
                self.sleep(.1)
            raise GameWait('팀 조회 응답 대기 시간 초과 · 게임이 안정되면 재시도합니다.')
        except (OSError,ValueError,KeyError,TypeError) as exc:
            if isinstance(exc,TeamReadPending):
                raise
            raise TeamReadPending('팀 조회 연결 확인 대기') from exc
        finally:
            for file in (request,response):
                try: file.unlink(missing_ok=True)
                except OSError: pass  # An active native read can briefly hold a Windows file handle; expiry still closes the query.
