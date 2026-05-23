<script lang="ts">
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';

	let { data } = $props();
</script>

<div class="space-y-4">
	<div>
		<h2 class="text-2xl font-bold tracking-tight">Traces</h2>
		<p class="text-muted-foreground">Phoenix trace visualization.</p>
	</div>

	<Card>
		<CardHeader>
			<CardTitle>Phoenix UI</CardTitle>
		</CardHeader>
		<CardContent>
			<iframe
				src={data.phoenixUrl}
				title="Phoenix Traces"
				class="w-full h-[calc(100vh-180px)] rounded-md border"
			></iframe>
		</CardContent>
	</Card>
</div>
