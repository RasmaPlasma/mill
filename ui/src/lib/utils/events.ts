export interface TimelineEvent {
	id: number | string;
	type: string;
	data: any;
	run_id?: string;
	time: Date;
}

export function getBadgeColor(type: string): string {
	if (type.startsWith('user.')) {
		return 'bg-pink-500/15 text-pink-500 border-pink-500/20';
	}
	if (type.startsWith('agent.')) {
		if (type === 'agent.thinking') return 'bg-purple-500/15 text-purple-500 border-purple-500/20';
		return 'bg-blue-500/15 text-blue-500 border-blue-500/20';
	}
	if (type === 'session.error') {
		return 'bg-red-500/15 text-red-500 border-red-500/20';
	}
	if (type.startsWith('session.')) {
		return 'bg-gray-500/15 text-gray-500 border-gray-500/20';
	}
	if (type.startsWith('span.')) {
		return 'bg-amber-500/15 text-amber-500 border-amber-500/20';
	}
	return 'bg-gray-500/15 text-gray-500 border-gray-500/20';
}

export function getTimelineColor(type: string): string {
	if (type.startsWith('user.')) return 'bg-pink-500';
	if (type === 'agent.thinking') return 'bg-purple-500';
	if (type.startsWith('agent.')) return 'bg-blue-500';
	if (type === 'session.error') return 'bg-red-500';
	if (type.startsWith('session.')) return 'bg-slate-400';
	if (type.startsWith('span.')) return 'bg-amber-500';
	return 'bg-slate-400';
}

export function getBadgeLabel(type: string): string {
	if (type === 'user.message') return 'User';
	if (type === 'user.interrupt') return 'Interrupt';
	if (type === 'agent.message') return 'Agent';
	if (type === 'agent.thinking') return 'Thinking';
	if (type === 'agent.tool_use') return 'Tool';
	if (type === 'agent.tool_result') return 'Tool';
	if (type === 'session.status_running') return 'Running';
	if (type === 'session.status_idle') return 'Idle';
	if (type === 'session.error') return 'Error';
	if (type === 'span.model_request_start') return 'Model';
	if (type === 'span.model_request_end') return 'Model';
	return type.split('.')[0].charAt(0).toUpperCase() + type.split('.')[0].slice(1);
}

export function getEventDisplayText(ev: TimelineEvent): string {
	const type = ev.type;
	const data = ev.data || {};
	switch (type) {
		case 'user.message':
			return data.content || data.text || '';
		case 'user.interrupt':
			return 'Interrupted';
		case 'agent.message':
			return data.content || '';
		case 'agent.thinking':
			return 'Thinking...';
		case 'agent.tool_use':
			return `${data.tool_name || 'Tool'} ${data.input ? JSON.stringify(data.input).slice(0, 60) : ''}`;
		case 'agent.tool_result':
			return `${data.tool_name || 'Tool'} → ${typeof data.output === 'string' ? data.output.slice(0, 60) : JSON.stringify(data.output ?? null).slice(0, 60)}`;
		case 'session.status_running':
			return 'Session running';
		case 'session.status_idle':
			return `Session idle${data.stop_reason ? `: ${data.stop_reason}` : ''}`;
		case 'session.error':
			return data.error?.message || data.error?.type || 'Error occurred';
		case 'span.model_request_end': {
			const u = data.model_usage || {};
			return `${u.input_tokens || 0} input → ${u.output_tokens || 0} output${u.cache_read_tokens ? ` · ${u.cache_read_tokens} cache read` : ''}${u.cache_write_tokens ? ` · ${u.cache_write_tokens} cache write` : ''}`;
		}
		default:
			return type;
	}
}

export function renderTranscript(ev: TimelineEvent): string {
	const type = ev.type;
	const data = ev.data || {};
	switch (type) {
		case 'user.message':
			return data.content || data.text || '';
		case 'agent.message':
			return data.content || '';
		case 'agent.thinking':
			return data.content || '';
		case 'agent.tool_use': {
			const name = data.tool_name || 'Tool';
			const input = data.input || {};
			return `${name}\n${JSON.stringify(input, null, 2)}`;
		}
		case 'agent.tool_result': {
			const name = data.tool_name || 'Tool';
			const out = typeof data.output === 'string' ? data.output : JSON.stringify(data.output, null, 2);
			return `${name} → ${out}`;
		}
		case 'session.error':
			return data.error?.message || data.error?.type || 'Error occurred';
		case 'session.status_running':
			return 'Session running';
		case 'session.status_idle':
			return data.stop_reason ? `Session idle: ${data.stop_reason}` : 'Session idle';
		case 'span.model_request_end': {
			const u = data.model_usage || {};
			let txt = `${u.input_tokens || 0} input → ${u.output_tokens || 0} output`;
			if (u.total_tokens) txt += ` · ${u.total_tokens} total`;
			if (u.cache_read_tokens) txt += ` · ${u.cache_read_tokens} cache read`;
			if (u.cache_write_tokens) txt += ` · ${u.cache_write_tokens} cache write`;
			return txt;
		}
		default:
			return JSON.stringify(data, null, 2);
	}
}
