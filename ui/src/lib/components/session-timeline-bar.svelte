<script lang="ts">
	import {
		Tooltip,
		TooltipContent,
		TooltipProvider,
		TooltipTrigger,
	} from '$lib/components/ui/tooltip';
	import { getTimelineColor, getBadgeLabel, type TimelineEvent } from '$lib/utils/events';

	interface Props {
		events: TimelineEvent[];
		sessionStart: Date;
		isRunning: boolean;
		onSelect: (event: TimelineEvent) => void;
	}

	let { events, sessionStart, isRunning, onSelect }: Props = $props();

	let now = $state(Date.now());

	$effect(() => {
		if (!isRunning) return;
		const id = setInterval(() => { now = Date.now(); }, 1000);
		return () => clearInterval(id);
	});

	const MIN_WIDTH_PCT = 0.35;
	const MAX_GAP_MS = 5000;
	const TAIL_MS = 2000;

	let segments = $state<Array<{
		event: TimelineEvent;
		leftPct: number;
		widthPct: number;
		durationMs: number;
	}>>([]);

	$effect(() => {
		const evs = events;

		// now state is only a dependency trigger for live updates while running
		const _ = now;
		// Read actual current time fresh to avoid clock skew from stale state
		const freshNow = Date.now();

		if (evs.length === 0) {
			segments = [];
			return;
		}

		// Build compressed timeline: gaps > MAX_GAP_MS are capped
		const compressedPositions: number[] = [];
		let compressedPos = 0;
		for (let i = 0; i < evs.length; i++) {
			compressedPositions.push(compressedPos);
			if (i < evs.length - 1) {
				const realGap = Math.max(evs[i + 1].time.getTime() - evs[i].time.getTime(), 0);
				compressedPos += Math.min(realGap, MAX_GAP_MS);
			}
		}

		// Trailing gap from last event to now (capped)
		const trailingGap = Math.min(Math.max(freshNow - evs[evs.length - 1].time.getTime(), 0), MAX_GAP_MS);
		const totalCompressed = compressedPos + trailingGap;

		if (totalCompressed === 0) {
			segments = [];
			return;
		}

		let offsetAccum = 0;
		let prevLeft = -1;

		segments = evs.map((ev, i) => {
			const next = evs[i + 1];
			const realEnd = next ? next.time.getTime() : freshNow;
			const durationMs = Math.max(realEnd - ev.time.getTime(), 0);

			const compressedGap = next
				? Math.min(Math.max(next.time.getTime() - ev.time.getTime(), 0), MAX_GAP_MS)
				: trailingGap;

			const rawLeft = (compressedPositions[i] / totalCompressed) * 100;
			const rawWidth = (compressedGap / totalCompressed) * 100;

			if (Math.abs(rawLeft - prevLeft) < 0.05) {
				offsetAccum += MIN_WIDTH_PCT;
			} else {
				offsetAccum = 0;
			}
			prevLeft = rawLeft;

			return {
				event: ev,
				leftPct: rawLeft + offsetAccum,
				widthPct: Math.max(rawWidth, MIN_WIDTH_PCT),
				durationMs,
			};
		});
	});

	function formatTime(d: Date): string {
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
	}

	function formatDurationMs(ms: number): string {
		if (ms < 1000) return `${ms}ms`;
		const s = Math.floor(ms / 1000);
		const m = Math.floor(s / 60);
		const h = Math.floor(m / 60);
		if (h > 0) return `${h}h ${m % 60}m ${s % 60}s`;
		if (m > 0) return `${m}m ${s % 60}s`;
		return `${s}s`;
	}
</script>

<TooltipProvider delayDuration={100}>
	<div class="h-5 w-full bg-muted/50 rounded-sm relative overflow-hidden">
		{#each segments as seg (seg.event.id)}
			<Tooltip>
				<TooltipTrigger
					class="absolute top-0 h-full border-r border-white/15 {getTimelineColor(seg.event.type)} transition-[width,left] duration-300 hover:brightness-110"
					style="left: {seg.leftPct}%; width: {seg.widthPct}%;"
					onclick={() => onSelect(seg.event)}
				>
				</TooltipTrigger>
				<TooltipContent side="top" sideOffset={4}>
					<div class="space-y-0.5">
						<div class="font-medium">{getBadgeLabel(seg.event.type)}</div>
						<div class="text-muted-foreground">{formatDurationMs(seg.durationMs)} · {formatTime(seg.event.time)}</div>
					</div>
				</TooltipContent>
			</Tooltip>
		{/each}
	</div>
</TooltipProvider>
