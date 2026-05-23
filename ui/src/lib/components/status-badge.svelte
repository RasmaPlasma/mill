<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';

	let { status }: { status: string } = $props();

	const variants: Record<string, string> = {
		idle: 'bg-secondary text-secondary-foreground',
		running: 'bg-green-500 text-white',
		creating: 'border border-input text-foreground',
		failed: 'bg-destructive text-destructive-foreground',
		terminated: 'bg-destructive text-destructive-foreground',
		archived: 'bg-secondary text-secondary-foreground opacity-50',
	};
</script>

<Badge class={variants[status] ?? 'bg-secondary text-secondary-foreground'}>
	{status}
</Badge>
