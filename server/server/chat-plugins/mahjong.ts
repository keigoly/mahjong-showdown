/**
 * Mahjong (Japanese riichi mahjong, 4 players) tables for mahjong-showdown.
 *
 * The game logic runs in a Python simulator (`sim/src/mjsim`, `python -m mjsim.stream`).
 * This plugin owns one simulator process and talks to it with JSON lines, routed by table id.
 * Each table is a GameRoom (`mahjong-<n>`) with a MahjongTable game attached.
 *
 * Commands:
 *   /mj search               - queue for a table; a table starts when 4 players are queued
 *   /mj cancel               - leave the queue
 *   /mj table A, B, C, D [, seed=N]  - start a table with these 4 users (same seed = same walls)
 *   /mj play                 - play against 3 simulator bots
 *   /choose RQID CHOICE      - answer a request (in the table room). CHOICE: "discard 5p [riichi]" / "call N" / "pass" / "win"
 *                              (/mj choose is the same)
 *   /mj autoplay on|off      - let the simulator play your seat (e.g. when you have to leave)
 *   /mj advice on|off        - turn the advisor on or off for your seat (practice tables only)
 *
 * Messages:
 *   |request|{json}          - only to the player who must decide (contains the full visible state)
 *   |mj|...                  - public events for everyone in the room (see sim/PROTOCOL.md)
 *   |mj|advice|{json}        - only to the player: the advisor's answer to the pending request (practice tables only)
 *   |mj|gameend|{json}       - final result (names, scores, ranks, points)
 *
 * Advice: if MJ_ADVISOR (or Config.mjadvisor) is set to an advisor's URL (e.g. http://127.0.0.1:8787/advise,
 * `python -m mjsim.advisor`), each request on a practice table (/mj play: one person + 3 simulator bots) is also
 * sent to the advisor, and its answer goes to that player only. Tables with two or more people never get advice.
 *
 * Derived from Pokémon Showdown's RoomGame plumbing (MIT). See NOTICE in the repository root.
 */

import * as child_process from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as readline from 'readline';

type SimMessage = {
	type: string,
	id?: string | null,
	player?: number | null,
	rqid?: number,
	request?: AnyObject,
	lines?: string[],
	message?: string,
	result?: AnyObject,
	log?: AnyObject | null,
};

const REPO_ROOT = path.resolve(process.cwd(), '..');
const SIM_SRC = path.join(REPO_ROOT, 'sim', 'src');
const DEFAULT_TIMEOUT = 60;
const LOG_DIR = path.join(process.cwd(), 'logs', 'mahjong');
// Save one log in every MJ_LOG_EVERY finished tables (large self-play runs fill the disk otherwise). 0 = none.
const LOG_EVERY = Number(process.env.MJ_LOG_EVERY ?? 1);
let finishedTables = 0;
const ADVISOR_TIMEOUT_MS = Number(process.env.MJ_ADVISOR_TIMEOUT_MS || 30000);

function advisorUrl(): string {
	return process.env.MJ_ADVISOR || (Config as AnyObject).mjadvisor || '';
}

function simPython(): string {
	if (process.env.MJSIM_PYTHON) return process.env.MJSIM_PYTHON;
	const venv = process.platform === 'win32' ?
		path.join(REPO_ROOT, 'sim', '.venv', 'Scripts', 'python.exe') :
		path.join(REPO_ROOT, 'sim', '.venv', 'bin', 'python');
	return fs.existsSync(venv) ? venv : (process.platform === 'win32' ? 'python' : 'python3');
}

class MjSimProcess {
	proc: child_process.ChildProcessWithoutNullStreams | null = null;
	tables = new Set<string>();
	constructor(readonly pool: MjSimPool, readonly index: number) {}

	ensure() {
		if (this.proc && this.proc.exitCode === null) return;
		const proc = child_process.spawn(simPython(), ['-m', 'mjsim.stream'], {
			cwd: REPO_ROOT,
			env: { ...process.env, PYTHONPATH: SIM_SRC, PYTHONUNBUFFERED: '1' },
		});
		this.proc = proc;
		readline.createInterface({ input: proc.stdout }).on('line', line => this.pool.onLine(line));
		readline.createInterface({ input: proc.stderr }).on('line', line => Monitor.warn(`[mjsim ${this.index}] ${line}`));
		proc.on('exit', code => {
			Monitor.warn(`[mjsim ${this.index}] simulator exited (${code})`);
			for (const id of this.tables) this.pool.tables.get(id)?.crash('The mahjong simulator stopped.');
			this.tables.clear();
			this.proc = null;
		});
	}

	send(msg: AnyObject) {
		this.ensure();
		this.proc!.stdin.write(JSON.stringify(msg) + '\n');
	}
}

/** シミュレーターのプロセスを複数持ち、卓を受け持ちの少ないプロセスに割り当てる (Python は 1 プロセス 1 コアのため)。 */
class MjSimPool {
	workers: MjSimProcess[] = [];
	tables = new Map<string, MahjongTable>();
	owner = new Map<string, MjSimProcess>();

	size() {
		const n = Number(process.env.MJSIM_PROCESSES || (Config as AnyObject).mjsimprocesses || 0);
		return n > 0 ? n : Math.max(1, Math.min(8, os.cpus().length - 2));
	}

	start(table: MahjongTable, msg: AnyObject) {
		while (this.workers.length < this.size()) this.workers.push(new MjSimProcess(this, this.workers.length));
		const worker = this.workers.reduce((a, b) => (b.tables.size < a.tables.size ? b : a));
		this.tables.set(table.tableId, table);
		this.owner.set(table.tableId, worker);
		worker.tables.add(table.tableId);
		worker.send(msg);
	}

	send(tableId: string, msg: AnyObject) {
		this.owner.get(tableId)?.send(msg);
	}

	release(tableId: string) {
		this.owner.get(tableId)?.tables.delete(tableId);
		this.owner.delete(tableId);
		this.tables.delete(tableId);
	}

	onLine(line: string) {
		let msg: SimMessage;
		try {
			msg = JSON.parse(line);
		} catch {
			Monitor.warn(`[mjsim] bad line: ${line.slice(0, 200)}`);
			return;
		}
		if (msg.type === 'ready') return;
		const table = msg.id ? this.tables.get(msg.id) : undefined;
		if (!table) return;
		table.onSim(msg);
	}
}

export const MjSim = new MjSimPool();

export class MahjongPlayer extends Rooms.RoomGamePlayer<MahjongTable> {
	seat: number;
	pending: { rqid: number, request: AnyObject } | null = null;
	/** 練習卓で助言を受けるか (/mj advice on|off)。 */
	advice = true;
	constructor(user: User | string | null, game: MahjongTable, seat: number) {
		super(user, game, seat + 1);
		this.seat = seat;
	}
}

let tableCounter = 0;

export class MahjongTable extends Rooms.RoomGame<MahjongPlayer> {
	override readonly gameid = 'mahjong' as ID;
	override title = 'Mahjong';
	seed: number;
	bots: (string | null)[];
	tableId: string;
	result: AnyObject | null = null;
	/** 練習卓 = 人が 1 人だけ (残りはシミュレーターのボット)。助言はこの卓だけ。 */
	practice: boolean;

	constructor(room: Room, users: (User | null)[], options: { seed?: number, rules?: string, timeout?: number, calls?: boolean }) {
		super(room);
		this.playerCap = 4;
		this.tableId = room.roomid;
		this.seed = options.seed ?? Math.floor(Math.random() * 2 ** 31);
		this.bots = users.map(u => (u ? null : 'efficiency'));
		this.practice = users.filter(u => u).length === 1;
		const names: string[] = [];
		users.forEach((user, seat) => {
			const player = new MahjongPlayer(user ?? `Bot ${seat + 1}`, this, seat);
			this.players.push(player);
			if (user) {
				this.playerTable[user.id] = player;
				user.joinRoom(room);
			}
			names.push(player.name);
		});
		MjSim.start(this, {
			type: 'start', id: this.tableId, names, seed: this.seed, rules: options.rules ?? 'tenhou-houou',
			calls: options.calls ?? true, timeout: options.timeout ?? DEFAULT_TIMEOUT, bots: this.bots,
		});
		room.add(`|mj|init|${names.join(',')}|${this.seed}`);
		if (this.practice) room.add(`|mj|practice|${advisorUrl() ? 'advice' : 'noadvice'}`);
		room.update();
	}

	/** 選手に送る要求の行。練習卓では、助言が後から届くかどうか (advice) も添える。 */
	requestLine(player: MahjongPlayer) {
		const { rqid, request } = player.pending!;
		const advice = this.advising(player);
		return `|request|${JSON.stringify({ rqid, ...request, practice: this.practice, advice })}`;
	}

	advising(player: MahjongPlayer) {
		return this.practice && player.advice && !!advisorUrl();
	}

	/** 助言役に要求を送り、答えをその選手にだけ送る。答える前に選手が打ったら捨てる。 */
	async advise(player: MahjongPlayer, rqid: number, request: AnyObject) {
		let advice: AnyObject;
		const t0 = Date.now();
		try {
			const res = await fetch(advisorUrl(), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ rqid, request: { rqid, ...request } }),
				signal: AbortSignal.timeout(ADVISOR_TIMEOUT_MS),
			});
			advice = res.ok ? await res.json() : { ok: false, error: `advisor returned HTTP ${res.status}` };
		} catch (err: any) {
			advice = { ok: false, error: err?.name === 'TimeoutError' ? 'advisor timed out' : `advisor unavailable (${err?.message})` };
		}
		if (this.ended || player.pending?.rqid !== rqid) return;
		player.sendRoom(`|mj|advice|${JSON.stringify({ ...advice, rqid, wait_ms: Date.now() - t0 })}`);
	}

	override makePlayer(user: User | string | null) {
		return new MahjongPlayer(user, this, this.players.length);
	}

	onSim(msg: SimMessage) {
		switch (msg.type) {
		case 'update':
			for (const line of msg.lines || []) this.room.add(line);
			this.room.update();
			break;
		case 'request': {
			const player = this.players[msg.player!];
			if (!player) break;
			player.pending = { rqid: msg.rqid!, request: msg.request! };
			player.sendRoom(this.requestLine(player));
			if (this.advising(player)) void this.advise(player, msg.rqid!, msg.request!);
			break;
		}
		case 'error':
			if (msg.player !== null && msg.player !== undefined) {
				this.players[msg.player]?.sendRoom(`|error|${msg.message}`);
			} else {
				Monitor.warn(`[mjsim] ${this.tableId}: ${msg.message}`);
				this.room.add(`|error|${msg.message}`).update();
			}
			break;
		case 'end':
			this.finish(msg.result || {}, msg.log || null);
			break;
		}
	}

	/** `/choose RQID CHOICE` (Showdown の共通コマンド) と `/mj choose` の両方から呼ばれる。 */
	override choose(user: User, text: string) {
		const [rqidText, ...rest] = text.trim().split(/\s+/);
		const rqid = parseInt(rqidText);
		if (isNaN(rqid) || !rest.length) throw new Chat.ErrorMessage(`Usage: /choose RQID CHOICE`);
		const player = this.playerTable[user.id];
		if (!player) throw new Chat.ErrorMessage(`You are not a player at this table.`);
		if (!player.pending || player.pending.rqid !== rqid) {
			throw new Chat.ErrorMessage(`That request (${rqid}) is not pending.`);
		}
		player.pending = null;
		MjSim.send(this.tableId, { type: 'choose', id: this.tableId, player: player.seat, rqid, choice: rest.join(' ') });
	}

	autoplay(user: User, on: boolean) {
		const player = this.playerTable[user.id];
		if (!player) throw new Chat.ErrorMessage(`You are not a player at this table.`);
		MjSim.send(this.tableId, { type: 'autoplay', id: this.tableId, player: player.seat, on });
	}

	setAdvice(user: User, on: boolean) {
		const player = this.playerTable[user.id];
		if (!player) throw new Chat.ErrorMessage(`You are not a player at this table.`);
		if (!this.practice) throw new Chat.ErrorMessage(`Advice is only for practice tables (/mj play).`);
		player.advice = on;
		if (on && player.pending && this.advising(player)) void this.advise(player, player.pending.rqid, player.pending.request);
	}

	override onConnect(user: User) {
		// 再接続したら、待っている要求を送り直す
		const player = this.playerTable[user.id];
		if (player?.pending) {
			player.sendRoom(this.requestLine(player));
			if (this.advising(player)) void this.advise(player, player.pending.rqid, player.pending.request);
		}
	}

	finish(result: AnyObject, log: AnyObject | null) {
		if (this.ended) return;
		this.result = result;
		this.room.add(`|mj|gameend|${JSON.stringify(result)}`).update();
		if (log && LOG_EVERY > 0 && finishedTables++ % LOG_EVERY === 0) {
			try {
				const month = new Date().toISOString().slice(0, 7);
				const dir = path.join(LOG_DIR, month);
				fs.mkdirSync(dir, { recursive: true });
				fs.writeFileSync(path.join(dir, `${this.tableId}.json`), JSON.stringify(log));
			} catch (err: any) {
				Monitor.warn(`[mahjong] could not save log for ${this.tableId}: ${err.message}`);
			}
		}
		MjSim.release(this.tableId);
		this.setEnded();
		const roomid = this.room.roomid;
		setTimeout(() => { Rooms.get(roomid)?.destroy(); }, 15 * 1000);
	}

	crash(reason: string) {
		this.room.add(`|error|${reason}`).update();
		this.finish({ crashed: true, reason }, null);
	}

	override destroy() {
		if (!this.ended) MjSim.send(this.tableId, { type: 'stop', id: this.tableId });
		MjSim.release(this.tableId);
		super.destroy();
	}
}

function createTable(users: (User | null)[], options: { seed?: number, rules?: string, timeout?: number } = {}) {
	tableCounter++;
	const roomid = `mahjong-${Date.now().toString(36)}${tableCounter}` as RoomID;
	const names = users.map((u, i) => (u ? u.name : `Bot ${i + 1}`));
	const room = Rooms.createGameRoom(roomid, `Mahjong: ${names.join(' / ')}`, { isPersonal: true });
	return new MahjongTable(room, users, options);
}

const searchQueue: ID[] = [];

function tryStartFromQueue() {
	while (searchQueue.length >= 4) {
		const ids = searchQueue.splice(0, 4);
		const users = ids.map(id => Users.getExact(id)).filter((u): u is User => !!u?.connected);
		if (users.length < 4) {
			for (const u of users) searchQueue.unshift(u.id);
			return;
		}
		createTable(users);
	}
}

export const commands: Chat.ChatCommands = {
	mj: {
		search(target, room, user) {
			if (searchQueue.includes(user.id)) throw new Chat.ErrorMessage(`You are already searching.`);
			searchQueue.push(user.id);
			this.sendReply(`|mj|searching|${searchQueue.length}`);
			tryStartFromQueue();
		},
		cancel(target, room, user) {
			const i = searchQueue.indexOf(user.id);
			if (i >= 0) searchQueue.splice(i, 1);
			this.sendReply(`|mj|cancelled`);
		},
		table(target, room, user) {
			// /mj table A, B, C, D [, seed=123] [, timeout=60]  (同じ seed なら同じ山の並び = 複製対局に使う)
			const parts = target.split(',').map(s => s.trim()).filter(Boolean);
			const options: { seed?: number, timeout?: number } = {};
			const names: string[] = [];
			for (const part of parts) {
				const [key, value] = part.split('=').map(s => s.trim());
				if (value !== undefined && key === 'seed') options.seed = parseInt(value);
				else if (value !== undefined && key === 'timeout') options.timeout = parseInt(value);
				else names.push(part);
			}
			if (names.length !== 4) throw new Chat.ErrorMessage(`Usage: /mj table A, B, C, D [, seed=N]`);
			const users = names.map(n => Users.get(n));
			if (users.some(u => !u?.connected)) throw new Chat.ErrorMessage(`All 4 users must be online.`);
			const table = createTable(users as User[], options);
			this.sendReply(`|mj|table|${table.roomid}|${table.seed}`);
		},
		play(target, room, user) {
			const table = createTable([user, null, null, null], { timeout: 300 });
			this.sendReply(`|mj|table|${table.roomid}`);
		},
		choose(target, room, user) {
			const game = this.requireGame(MahjongTable);
			game.choose(user, target);
		},
		autoplay(target, room, user) {
			const game = this.requireGame(MahjongTable);
			game.autoplay(user, target.trim() !== 'off');
			this.sendReply(`|mj|autoplay|${target.trim() !== 'off' ? 'on' : 'off'}`);
		},
		advice(target, room, user) {
			const game = this.requireGame(MahjongTable);
			const on = target.trim() !== 'off';
			game.setAdvice(user, on);
			this.sendReply(`|mj|advicemode|${on ? 'on' : 'off'}`);
		},
		''(target, room, user) {
			this.parse('/help mj');
		},
	},
	mjhelp: [
		`/mj search - Queue for a 4-player mahjong table.`,
		`/mj cancel - Leave the queue.`,
		`/mj table A, B, C, D - Start a table with these users.`,
		`/mj play - Play against 3 simulator bots.`,
		`/mj choose RQID CHOICE - Answer a request: "discard 5p [riichi]", "call N", "pass", "win".`,
		`/mj autoplay on|off - Let the simulator play your seat.`,
		`/mj advice on|off - Turn the advisor on or off for your seat (practice tables only).`,
	],
};
