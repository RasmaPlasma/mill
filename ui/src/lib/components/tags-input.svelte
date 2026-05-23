<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { X } from 'lucide-svelte';

	let { value = $bindable<string[]>([]), placeholder = 'Add item...' } = $props();
	let inputValue = $state('');

	function addTag() {
		const trimmed = inputValue.trim();
		if (trimmed && !value.includes(trimmed)) {
			value = [...value, trimmed];
			inputValue = '';
		}
	}

	function removeTag(tag: string) {
		value = value.filter((t) => t !== tag);
	}

	function onkeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ',') {
			e.preventDefault();
			addTag();
		} else if (e.key === 'Backspace' && !inputValue && value.length > 0) {
			value = value.slice(0, -1);
		}
	}
</script>

<div class="flex flex-wrap items-center gap-2 rounded-md border px-2 py-1 min-h-10">
	{#each value as tag (tag)}
		<Badge variant="secondary" class="gap-1">
			{tag}
			<button type="button" onclick={() => removeTag(tag)} class="hover:text-destructive">
				<X class="h-3 w-3" />
			</button>
		</Badge>
	{/each}
	<Input
		type="text"
		{placeholder}
		class="flex-1 border-0 shadow-none focus-visible:ring-0 min-w-[120px] h-7 px-1"
		bind:value={inputValue}
		onkeydown={onkeydown}
		onblur={addTag}
	/>
</div>
