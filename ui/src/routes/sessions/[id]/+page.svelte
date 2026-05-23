<script lang="ts">
	import { superForm } from 'sveltekit-superforms';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { ScrollArea } from '$lib/components/ui/scroll-area';
	import { Input } from '$lib/components/ui/input';
	import * as Select from '$lib/components/ui/select';
	import {
		Popover,
		PopoverContent,
		PopoverTrigger,
	} from '$lib/components/ui/popover';
	import { toast } from 'svelte-sonner';
	import { onMount, tick, untrack } from 'svelte';
	import {
		ArrowLeft,
		Loader2,
		Send,
		Square,
		Activity,
		RefreshCw,
		Copy,
		Check,
		X,
		Clock,
		Zap,
		User,
		Bot,
		Wrench,
		AlertCircle,
		Terminal,
		ChevronRight,
		ChevronDown,
		ArrowDown,
	} from 'lucide-svelte';
	import Prism from 'prismjs';
	import 'prismjs/components/prism-json';
	import 'prismjs/themes/prism-tomorrow.css';
	import SessionTimelineBar from '$lib/components/session-timeline-bar.svelte';
	import SessionEventTranscript from '$lib/components/session-event-transcript.svelte';
	import { getBadgeColor, getBadgeLabel, getEventDisplayText, type TimelineEvent } from '$lib/utils/events';

	let { data } = $props();

	// --- State ---
	let es = $state<EventSource | null>(null);
	let isConnected = $state(false);
	let isRunning = $state(false);
	let inputMessage = $state('');
	let scrollViewport = $state<HTMLElement | null>(null);
	let eventFilter = $state('all');
	let selectedEvent = $state<any>(null);
	let detailViewMode = $state<'transcript' | 'debug'>('transcript');
	let copiedId = $state(false);
	let showDetailPanel = $state(false);
	let stickToBottom = $state(true);
	let showNewEventsIndicator = $state(false);

	// All events (single timeline source of truth)
	let allEvents = $state<TimelineEvent[]>([]);

	let seenEventIds = $state<Set<number | string>>(new Set());
	let stopReason = $state<string | null>(data.session.stop_reason || null);

	// --- Helpers ---
	function isRawEventType(type: string): boolean {
		return ['values', 'metadata', 'end', 'error', 'on_chat_model_start', 'on_chat_model_stream', 'on_chat_model_end', 'on_tool_start', 'on_tool_end'].includes(type);
	}

	function formatTime(d: Date) {
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
	}

	function formatDuration(seconds: number): string {
		const d = Math.floor(seconds / 86400);
		const h = Math.floor((seconds % 86400) / 3600);
		const m = Math.floor((seconds % 3600) / 60);
		if (d > 0) return `${d}d ${h}h`;
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}

	function timeAgo(d: Date): string {
		const now = new Date();
		const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
		if (diff < 60) return 'just now';
		if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`;
		if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
		return `${Math.floor(diff / 86400)} days ago`;
	}

	function truncateId(id: string | null) {
		if (!id) return '-';
		return id.length > 12 ? id.slice(0, 12) : id;
	}

	function getSessionDuration(): string {
		if (!data.session.created_at) return '-';
		const created = new Date(data.session.created_at);
		const now = new Date();
		const diff = Math.floor((now.getTime() - created.getTime()) / 1000);
		return formatDuration(diff);
	}

	function getLastActivity(): string {
		if (allEvents.length === 0) return '-';
		const last = allEvents[allEvents.length - 1];
		return timeAgo(last.time);
	}

	function getLastActivityExact(): string {
		if (allEvents.length === 0) return '-';
		const last = allEvents[allEvents.length - 1];
		return last.time.toLocaleString();
	}

	function highlightJson(obj: any): string {
		const json = JSON.stringify(obj, null, 2);
		return Prism.highlight(json, Prism.languages.json, 'json');
	}

	// --- Init ---
	function initFromServerEvents() {
		if (!data.events?.length) return;
		const batch: TimelineEvent[] = [];
		const newIds = new Set(seenEventIds);
		for (const ev of data.events) {
			if (isRawEventType(ev.event_type)) continue;
			const eventId = ev.id;
			if (eventId && newIds.has(eventId)) continue;
			if (eventId) newIds.add(eventId);
			const evTime = parseServerTime({
				id: ev.id,
				type: ev.event_type,
				data: ev.payload,
				run_id: ev.run_id,
				timestamp: ev.created_at,
			});
			batch.push({
				id: eventId || Date.now(),
				type: ev.event_type,
				data: ev.payload || {},
				run_id: ev.run_id,
				time: evTime,
			});
		}
		if (batch.length > 0) {
			seenEventIds = newIds;
			allEvents = [...allEvents, ...batch];
		}
	}

	// --- Event Batching ---
	let eventBuffer: any[] = [];
	let flushScheduled = false;

	function queueEvent(event: any) {
		eventBuffer.push(event);
		if (!flushScheduled) {
			flushScheduled = true;
			requestAnimationFrame(() => {
				flushEvents();
			});
		}
	}

	function flushEvents() {
		flushScheduled = false;
		if (eventBuffer.length === 0) return;

		const batch = eventBuffer;
		eventBuffer = [];

		const newIds = new Set(seenEventIds);
		const newEvents: TimelineEvent[] = [];

		for (const event of batch) {
			const eventId = event.id;
			if (eventId && newIds.has(eventId)) continue;
			if (eventId) newIds.add(eventId);

			const evTime = parseServerTime(event);
			const type = event.type || 'message';
			const data = event.data || {};

			newEvents.push({
				id: eventId || Date.now(),
				type,
				data,
				run_id: event.run_id,
				time: evTime,
			});

			if (type === 'session.status_running') {
				isRunning = true;
				stopReason = null;
			} else if (type === 'session.status_idle') {
				isRunning = false;
				if (data.stop_reason) stopReason = data.stop_reason;
			} else if (type === 'session.error') {
				isRunning = false;
			}
		}

		if (newEvents.length > 0) {
			seenEventIds = newIds;
			allEvents = [...allEvents, ...newEvents];
		}
	}

	function parseServerTime(event: any): Date {
		if (event.timestamp) {
			const d = new Date(event.timestamp);
			if (!isNaN(d.getTime())) return d;
		}
		if (event.created_at) {
			const d = new Date(event.created_at);
			if (!isNaN(d.getTime())) return d;
		}
		return new Date();
	}

	// --- SSE ---
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

	function connectStream() {
		if (!data?.session?.id) return;
		if (es) { es.close(); es = null; }
		if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
		isConnected = false;

		const lastEvent = allEvents.length > 0 ? allEvents[allEvents.length - 1] : null;
		const since = lastEvent ? lastEvent.time.toISOString() : null;
		const streamUrl = since
			? `/api/sessions/${data.session.id}/events/stream?since=${encodeURIComponent(since)}`
			: `/api/sessions/${data.session.id}/events/stream`;
		es = new EventSource(streamUrl);

		es.onopen = () => { isConnected = true; };
		es.onmessage = (ev) => {
			try { queueEvent(JSON.parse(ev.data)); } catch (e) {}
		};
		es.onerror = () => {
			isConnected = false;
			if (es) { es.close(); es = null; }
			const backoff = Math.min(3000 * (1 + allEvents.filter(e => e.type === 'session.error').length), 30000);
			reconnectTimer = setTimeout(() => {
				if (!es && data?.session?.id) connectStream();
			}, backoff);
		};
	}

	// --- SuperForm ---
	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		applyAction: false,
		invalidateAll: false,
		onResult: ({ result }) => {
			if (result.type === 'success') {
				// Don't add optimistic user.message — wait for SSE delivery.
				// Backend publishes user.message to Redis Stream after DB save,
				// so it arrives via SSE within ~100ms. This avoids duplicates
				// since the synthetic client-side ID won't match the real DB ID.
				inputMessage = '';
				toast.success('Message sent');
				isRunning = true;
				stickToBottom = true;
			}
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
		},
	});

	async function stopStream() {
		// Do NOT close SSE — we need to receive the user.interrupt
		// and session.status_idle events that the backend will emit.
		try {
			const resp = await fetch(`?/interrupt`, { method: 'POST', body: new FormData() });
			const result = await resp.json();
			if (result.type === 'success') {
				toast.success('Agent stopped');
			} else {
				toast.error(result.data?.error || 'Failed to stop agent');
			}
		} catch (err: any) {
			toast.error(err.message || 'Failed to stop agent');
		}
	}

	function selectEvent(ev: any) {
		selectedEvent = ev;
		showDetailPanel = true;
	}

	function scrollToEvent(eventId: number | string) {
		const el = document.getElementById(`event-${eventId}`);
		if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
	}

	function closeDetailPanel() {
		showDetailPanel = false;
		selectedEvent = null;
	}

	async function copySessionId() {
		try {
			await navigator.clipboard.writeText(data.session.id);
			copiedId = true;
			setTimeout(() => copiedId = false, 2000);
		} catch {}
	}

	function isNearBottom(): boolean {
		const el = scrollViewport;
		if (!el) return true;
		return el.scrollHeight - el.scrollTop - el.clientHeight < 100;
	}

	function handleScroll() {
		stickToBottom = isNearBottom();
		showNewEventsIndicator = !stickToBottom && allEvents.length > 0;
	}

	async function scrollToBottom(force = false) {
		if (force || stickToBottom) {
			await tick();
			scrollViewport?.scrollTo({ top: scrollViewport.scrollHeight, behavior: 'instant' });
		}
	}

	function handleJumpToBottom() {
		stickToBottom = true;
		scrollToBottom(true);
	}

	// Auto-scroll when new events arrive (only if at bottom)
	$effect(() => {
		const count = allEvents.length;
		if (count > 0) {
			scrollToBottom();
		}
	});

	// Re-engage auto-scroll when session starts running
	$effect(() => {
		if (isRunning) {
			stickToBottom = true;
			scrollToBottom(true);
		}
	});

	function handleKeydown(ev: KeyboardEvent) {
		if (ev.key === 'Enter' && !ev.shiftKey && inputMessage.trim()) {
			ev.preventDefault();
			const formEl = document.querySelector('form[action="?/sendEvent"]') as HTMLFormElement;
			if (formEl) formEl.requestSubmit();
		}
	}

	onMount(() => {
		initFromServerEvents();
		connectStream();
		return () => {
			if (es) { es.close(); es = null; }
			if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
		};
	});

	$effect(() => {
		isRunning = data.session.status === 'running';
	});

	// --- Derived ---
	const filteredEvents = $derived(() => {
		let list = allEvents;
		if (eventFilter !== 'all') {
			list = list.filter(e => e.type === eventFilter);
		}
		return list;
	});

	const uniqueEventTypes = $derived(
		['all', ...new Set(allEvents.map(e => e.type))]
	);

	// Agent info for header
	const agentName = $derived(data.agentDetails?.name || '-');
	const agentDescription = $derived(data.agentDetails?.description || '');
	const agentModel = $derived(data.agentDetails?.llm_model?.provider_model || data.agentDetails?.model || '-');
	const agentVersion = $derived(data.agentDetails?.version || '-');
	const agentId = $derived(data.agentDetails?.id || '');

	// Env info for header
	const envName = $derived(data.envDetails?.name || '-');
	const envState = $derived(data.envDetails?.state || 'Active');
	const envScope = $derived(data.envDetails?.scope || 'Organization');
	const envCreated = $derived(data.envDetails?.created_at || '');
	const envId = $derived(data.envDetails?.id || '');
</script>

<div class="h-full flex flex-col overflow-hidden">
	<!-- Compact Header -->
	<div class="border-b px-4 py-2.5 flex items-center justify-between shrink-0">
		<div class="flex items-center gap-3 min-w-0">
			<Button variant="ghost" size="icon" class="h-7 w-7 shrink-0" href="/sessions">
				<ArrowLeft class="h-4 w-4" />
			</Button>
			<div class="flex items-center gap-2 min-w-0">
				<h1 class="text-sm font-semibold tracking-tight truncate">
					{truncateId(data.session.id)}
				</h1>
				<Badge variant="outline" class="text-[10px] h-4 shrink-0">
					{data.session.status}
				</Badge>
				{#if stopReason && !isRunning}
					<Badge variant="outline" class="text-[10px] h-4 shrink-0">
						{stopReason}
					</Badge>
				{/if}
			</div>
			<div class="h-4 w-px bg-border mx-1 shrink-0" />
			<!-- Agent Pill -->
			{#if agentName !== '-'}
				<Popover>
				<PopoverTrigger>
					{#snippet child({ props })}
						<button {...props} class="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors shrink-0">
							<Bot class="h-3.5 w-3.5" />
							<span class="truncate max-w-[120px]">{agentName}</span>
							<ChevronDown class="h-3 w-3" />
						</button>
					{/snippet}
				</PopoverTrigger>
					<PopoverContent class="w-80 p-0" align="start">
						<div class="p-3 space-y-3">
							<div class="font-medium text-sm">{agentName}</div>
							{#if agentDescription}
								<p class="text-xs text-muted-foreground">{agentDescription}</p>
							{/if}
							<div class="space-y-1.5 text-xs">
								<div class="flex justify-between">
									<span class="text-muted-foreground">Model</span>
									<span>{agentModel}</span>
								</div>
								<div class="flex justify-between">
									<span class="text-muted-foreground">Version</span>
									<span>{agentVersion}</span>
								</div>
								<div class="flex justify-between">
									<span class="text-muted-foreground">ID</span>
									<span class="font-mono">{truncateId(agentId)}</span>
								</div>
							</div>
							{#if agentId}
								<a href="/agents/{agentId}" class="text-xs text-primary hover:underline flex items-center gap-1">
									View details
									<ChevronRight class="h-3 w-3" />
								</a>
							{/if}
						</div>
					</PopoverContent>
				</Popover>
			{/if}
			<!-- Env Icon -->
			{#if envId}
				<Popover>
				<PopoverTrigger>
					{#snippet child({ props })}
						<button {...props} class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors shrink-0">
							<Terminal class="h-3.5 w-3.5" />
							<span class="truncate max-w-[80px]">{envName}</span>
							<ChevronDown class="h-3 w-3" />
						</button>
					{/snippet}
				</PopoverTrigger>
					<PopoverContent class="w-72 p-0" align="start">
						<div class="p-3 space-y-3">
							<div class="font-medium text-sm">{envName}</div>
							<div class="space-y-1.5 text-xs">
								<div class="flex justify-between">
									<span class="text-muted-foreground">State</span>
									<span>{envState}</span>
								</div>
								<div class="flex justify-between">
									<span class="text-muted-foreground">Scope</span>
									<span>{envScope}</span>
								</div>
								{#if envCreated}
									<div class="flex justify-between">
										<span class="text-muted-foreground">Created</span>
										<span>{new Date(envCreated).toLocaleDateString()}</span>
									</div>
								{/if}
								<div class="flex justify-between">
									<span class="text-muted-foreground">ID</span>
									<span class="font-mono">{truncateId(envId)}</span>
								</div>
							</div>
							{#if envId}
								<a href="/environments/{envId}" class="text-xs text-primary hover:underline flex items-center gap-1">
									View details
									<ChevronRight class="h-3 w-3" />
								</a>
							{/if}
						</div>
					</PopoverContent>
				</Popover>
			{/if}
			<!-- Duration -->
			<Popover>
			<PopoverTrigger>
				{#snippet child({ props })}
					<button {...props} class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors shrink-0">
						<Clock class="h-3.5 w-3.5" />
						<span>{getSessionDuration()}</span>
					</button>
				{/snippet}
			</PopoverTrigger>
				<PopoverContent class="w-64" align="start">
					<div class="space-y-1.5 text-xs">
						<div class="font-medium">Duration</div>
						<div class="flex justify-between">
							<span class="text-muted-foreground">Wall-clock since created</span>
							<span>{getSessionDuration()}</span>
						</div>
					</div>
				</PopoverContent>
			</Popover>
			<!-- Last Activity -->
			<Popover>
			<PopoverTrigger>
				{#snippet child({ props })}
					<button {...props} class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors shrink-0">
						<Zap class="h-3.5 w-3.5" />
						<span>{getLastActivity()}</span>
					</button>
				{/snippet}
			</PopoverTrigger>
				<PopoverContent class="w-64" align="start">
					<div class="space-y-1.5 text-xs">
						<div class="font-medium">Last activity</div>
						<div class="text-muted-foreground">{getLastActivityExact()}</div>
					</div>
				</PopoverContent>
			</Popover>
		</div>
		<div class="flex items-center gap-2 shrink-0">
			{#if isConnected}
				<Badge variant="outline" class="text-[10px] h-4 gap-1">
					<Activity class="h-2.5 w-2.5 text-chart-1" />
					Live
				</Badge>
			{:else}
				<Badge variant="outline" class="text-[10px] h-4 gap-1 text-muted-foreground">
					<Activity class="h-2.5 w-2.5" />
					Offline
				</Badge>
			{/if}
			<Button variant="ghost" size="icon" class="h-7 w-7" onclick={copySessionId} title="Copy session ID">
				{#if copiedId}
					<Check class="h-3.5 w-3.5 text-chart-1" />
				{:else}
					<Copy class="h-3.5 w-3.5" />
				{/if}
			</Button>
			{#if !isConnected}
				<Button variant="ghost" size="icon" class="h-7 w-7" onclick={() => connectStream()} title="Reconnect">
					<RefreshCw class="h-3.5 w-3.5" />
				</Button>
			{/if}
			{#if isRunning}
				<Button variant="ghost" size="icon" class="h-7 w-7 text-destructive" onclick={() => stopStream()} title="Stop">
					<Square class="h-3.5 w-3.5" />
				</Button>
			{/if}
		</div>
	</div>

	<!-- Filter Bar -->
	<div class="border-b px-4 shrink-0 flex items-center justify-end py-1.5">
		<Select.Root type="single" bind:value={eventFilter}>
			<Select.Trigger class="h-6 text-xs w-36">
				<Select.Value placeholder="All events" />
			</Select.Trigger>
			<Select.Content>
				{#each uniqueEventTypes as t}
					<Select.Item value={t} label={t} class="text-xs">{t}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
	</div>

	<!-- Timeline Bar -->
	<div class="border-b px-4 py-1 shrink-0">
		<SessionTimelineBar
			events={allEvents}
			sessionStart={new Date(data.session.created_at)}
			{isRunning}
			onSelect={(ev) => { selectEvent(ev); scrollToEvent(ev.id); }}
		/>
	</div>

	<!-- Timeline + Detail Panel -->
	<div class="flex-1 flex overflow-hidden relative">
		<!-- Timeline -->
		<div class="flex-1 flex flex-col min-w-0" class:w-full={!showDetailPanel} class:w-[60%]={showDetailPanel}>
			<ScrollArea class="flex-1 min-h-0" bind:viewportRef={scrollViewport}>
				<div class="p-2" onscroll={handleScroll}>
					{#if filteredEvents().length === 0}
						<div class="flex flex-col items-center justify-center h-full py-20 text-muted-foreground">
							<p class="text-sm">No events yet.</p>
							<p class="text-xs">Send a message to start the conversation.</p>
						</div>
					{:else}
						<div class="space-y-0.5">
							{#each filteredEvents() as ev (ev.id)}
								<button
									id="event-{ev.id}"
									class="w-full text-left grid grid-cols-[56px_1fr_auto] gap-2 px-2 py-1.5 rounded hover:bg-muted/50 transition-colors group items-baseline"
									onclick={() => selectEvent(ev)}
									class:bg-muted={selectedEvent?.id === ev.id}
								>
									<!-- Badge -->
									<div class="flex items-center">
										<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border {getBadgeColor(ev.type)}">
											{getBadgeLabel(ev.type)}
										</span>
									</div>
									<!-- Content -->
									<div class="min-w-0">
										<p class="text-xs text-foreground truncate">
											{getEventDisplayText(ev)}
										</p>
										{#if ev.type === 'agent.thinking' && ev.data.content}
											<p class="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">
												{ev.data.content}
											</p>
										{/if}
									</div>
									<!-- Timestamp -->
									<div class="text-[10px] text-muted-foreground tabular-nums">
										{formatTime(ev.time)}
									</div>
								</button>
							{/each}
						</div>
					{/if}
				</div>
				{#if showNewEventsIndicator}
					<div class="absolute bottom-3 left-1/2 -translate-x-1/2 z-10">
						<Button
							size="sm"
							class="h-7 gap-1.5 rounded-full px-3 text-xs shadow-lg"
							onclick={handleJumpToBottom}
						>
							<ArrowDown class="h-3 w-3" />
							New events
						</Button>
					</div>
				{/if}
			</ScrollArea>
		</div>

		<!-- Detail Inspector Panel -->
		{#if showDetailPanel && selectedEvent}
			<div class="w-[40%] border-l bg-card flex flex-col shrink-0">
				<div class="border-b px-3 py-2 flex items-center justify-between shrink-0">
					<div class="flex items-center gap-2">
						<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border {getBadgeColor(selectedEvent.type)}">
							{getBadgeLabel(selectedEvent.type)}
						</span>
						<span class="text-xs text-muted-foreground">{formatTime(selectedEvent.time)}</span>
					</div>
					<div class="flex items-center gap-2">
						<!-- Transcript / Debug Pill Toggle -->
						<div class="flex items-center rounded-md border overflow-hidden bg-muted/50">
							<Button
								variant={detailViewMode === 'transcript' ? 'secondary' : 'ghost'}
								size="sm"
								class="h-5 text-[10px] px-2 rounded-none border-0"
								onclick={() => detailViewMode = 'transcript'}
							>
								Transcript
							</Button>
							<div class="w-px h-3 bg-border" />
							<Button
								variant={detailViewMode === 'debug' ? 'secondary' : 'ghost'}
								size="sm"
								class="h-5 text-[10px] px-2 rounded-none border-0"
								onclick={() => detailViewMode = 'debug'}
							>
								Debug
							</Button>
						</div>
						<Button variant="ghost" size="icon" class="h-6 w-6" onclick={closeDetailPanel}>
							<X class="h-3.5 w-3.5" />
						</Button>
					</div>
				</div>
				<ScrollArea class="flex-1 min-h-0">
					<div class="p-3">
						{#if detailViewMode === 'transcript'}
							<SessionEventTranscript event={selectedEvent} />
						{:else}
							<div class="text-xs font-mono leading-relaxed">
								<pre class="whitespace-pre-wrap break-all"><code>{@html highlightJson(selectedEvent.data)}</code></pre>
							</div>
						{/if}
					</div>
				</ScrollArea>
			</div>
		{/if}
	</div>

	<!-- Composer -->
	<div class="border-t px-4 py-2 shrink-0">
		<form method="POST" action="?/sendEvent" use:enhance class="flex gap-2 items-center">
			<Input
				name="message"
				placeholder={isRunning ? 'Agent is thinking...' : 'Send a message to the agent'}
				bind:value={inputMessage}
				disabled={isRunning || $submitting}
				class="h-8 text-sm"
				onkeydown={handleKeydown}
			/>
			<Button
				type="submit"
				disabled={isRunning || $submitting || $delayed || !inputMessage.trim()}
				size="sm"
				class="h-8 px-3 text-xs shrink-0"
			>
				{#if $submitting || $delayed}
					<Loader2 class="mr-1 h-3 w-3 animate-spin" />
					Sending...
				{:else}
					<Send class="mr-1 h-3 w-3" />
					Send <span class="text-muted-foreground ml-1">· Enter</span>
				{/if}
			</Button>
		</form>
		{#if $errors.message}<p class="text-xs text-destructive mt-1">{$errors.message}</p>{/if}
	</div>
</div>
