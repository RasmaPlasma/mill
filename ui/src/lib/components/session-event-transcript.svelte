<script lang="ts">
	import type { TimelineEvent } from '$lib/utils/events';
	import MarkdownCard from './transcript/markdown-card.svelte';
	import ShellCard from './transcript/shell-card.svelte';
	import FileWriteCard from './transcript/file-write-card.svelte';
	import FileEditCard from './transcript/file-edit-card.svelte';
	import FileReadCard from './transcript/file-read-card.svelte';
	import DirListCard from './transcript/dir-list-card.svelte';
	import TodoListCard from './transcript/todo-list-card.svelte';
	import ExecuteResultCard from './transcript/execute-result-card.svelte';
	import ErrorCard from './transcript/error-card.svelte';
	import StatusPill from './transcript/status-pill.svelte';
	import UsageMetrics from './transcript/usage-metrics.svelte';
	import Prism from 'prismjs';
	import 'prismjs/components/prism-json';

	let { event }: { event: TimelineEvent } = $props();

	function prettyJson(obj: any): string {
		return JSON.stringify(obj, null, 2);
	}

	function highlightJson(obj: any): string {
		const json = JSON.stringify(obj, null, 2);
		return Prism.highlight(json, Prism.languages.json, 'json');
	}
</script>

<div class="space-y-3">
	{#if event.type === 'agent.message'}
		<MarkdownCard content={event.data?.content || ''} variant="agent" />

	{:else if event.type === 'agent.thinking'}
		<MarkdownCard content={event.data?.content || ''} variant="thinking" />

	{:else if event.type === 'user.message'}
		<MarkdownCard content={event.data?.content || event.data?.text || ''} variant="user" />

	{:else if event.type === 'agent.tool_use'}
		{@const toolName = event.data?.tool_name || 'unknown'}
		{@const input = event.data?.input || {}}
		{#if toolName === 'execute'}
			<ShellCard command={input.command || ''} timeout={input.timeout} />
		{:else if toolName === 'write_file'}
			<FileWriteCard filePath={input.file_path || ''} content={input.content || ''} />
		{:else if toolName === 'edit_file'}
			<FileEditCard
				filePath={input.file_path || ''}
				oldString={input.old_string || ''}
				newString={input.new_string || ''}
			/>
		{:else if toolName === 'read_file'}
			<div class="rounded border bg-muted/30 overflow-hidden">
				<div class="flex items-center gap-2 px-2.5 py-1.5 border-b bg-muted/50">
					<span class="text-[10px] font-medium text-muted-foreground font-mono">{input.file_path || '?'}</span>
					{#if input.limit}<span class="text-[10px] text-muted-foreground ml-auto">limit: {input.limit}</span>{/if}
					{#if input.offset}<span class="text-[10px] text-muted-foreground">offset: {input.offset}</span>{/if}
				</div>
				<div class="px-3 py-2 text-xs text-muted-foreground italic">Read file (see result event for content)</div>
			</div>
		{:else if toolName === 'ls'}
			<div class="rounded border bg-muted/30 overflow-hidden">
				<div class="px-3 py-2 text-xs font-mono text-foreground">ls {input.path || '.'}</div>
			</div>
		{:else if toolName === 'write_todos'}
			<TodoListCard output={prettyJson(input.todos || [])} />
		{:else}
			<div class="rounded border bg-muted/30 overflow-hidden">
				<div class="px-2.5 py-1.5 border-b bg-muted/50 text-[10px] font-medium text-muted-foreground uppercase">{toolName}</div>
				<pre class="px-3 py-2 text-xs font-mono overflow-x-auto"><code>{@html highlightJson(input)}</code></pre>
			</div>
		{/if}

	{:else if event.type === 'agent.tool_result'}
		{@const toolName = event.data?.tool_name || 'unknown'}
		{@const output = event.data?.output}
		{#if toolName === 'execute'}
			<ExecuteResultCard output={typeof output === 'string' ? output : JSON.stringify(output)} />
		{:else if toolName === 'write_file'}
			<div class="text-xs text-foreground">{typeof output === 'string' ? output : JSON.stringify(output)}</div>
		{:else if toolName === 'edit_file'}
			<div class="text-xs text-foreground">{typeof output === 'string' ? output : JSON.stringify(output)}</div>
		{:else if toolName === 'read_file'}
			<FileReadCard filePath={event.data?.tool_name || ''} content={typeof output === 'string' ? output : JSON.stringify(output, null, 2)} />
		{:else if toolName === 'ls'}
			<DirListCard output={typeof output === 'string' ? output : JSON.stringify(output)} />
		{:else if toolName === 'write_todos'}
			<TodoListCard output={typeof output === 'string' ? output : JSON.stringify(output)} />
		{:else}
			<div class="rounded border bg-muted/30 overflow-hidden">
				<div class="px-2.5 py-1.5 border-b bg-muted/50 text-[10px] font-medium text-muted-foreground uppercase">{toolName} result</div>
				<pre class="px-3 py-2 text-xs font-mono overflow-x-auto"><code>{@html highlightJson(output)}</code></pre>
			</div>
		{/if}

	{:else if event.type === 'session.error'}
		<ErrorCard error={event.data?.error || {}} />

	{:else if event.type === 'session.status_running'}
		<StatusPill status="running" />

	{:else if event.type === 'session.status_idle'}
		<StatusPill status="idle" stopReason={event.data?.stop_reason} />

	{:else if event.type === 'span.model_request_end'}
		<UsageMetrics usage={event.data?.model_usage || {}} />

	{:else}
		<!-- Fallback: pretty-printed JSON -->
		<div class="rounded border bg-muted/30 overflow-hidden">
			<div class="px-2.5 py-1.5 border-b bg-muted/50 text-[10px] font-medium text-muted-foreground uppercase">{event.type}</div>
			<pre class="px-3 py-2 text-xs font-mono overflow-x-auto"><code>{@html highlightJson(event.data)}</code></pre>
		</div>
	{/if}
</div>
