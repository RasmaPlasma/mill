<script lang="ts">
	import '../app.css';
	import '@fontsource-variable/inter';
	import '@fontsource/instrument-serif';
	import { Toaster } from '$lib/components/ui/sonner';
	import AppSidebar from '$lib/components/app-sidebar.svelte';
	import { ModeWatcher } from 'mode-watcher';

	let { children } = $props();
</script>

<ModeWatcher />
<Toaster position="bottom-right" richColors />

<div class="flex h-screen bg-background overflow-hidden">
	<AppSidebar />

	<div class="flex-1 flex flex-col min-w-0">
		<main class="flex-1 overflow-auto p-4 lg:p-6">
			{@render children()}
		</main>
	</div>
</div>
