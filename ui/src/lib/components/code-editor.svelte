<script lang="ts">
	import { browser } from '$app/environment';

	let {
		value = $bindable(''),
		placeholder = '',
		class: className = ''
	} = $props();

	let CodeMirror = $state<any>(null);
	let markdownLang = $state<any>(null);
	let theme = $state<any>(null);

	$effect(() => {
		if (browser && !CodeMirror) {
			Promise.all([
				import('svelte-codemirror-editor'),
				import('@codemirror/lang-markdown'),
				import('@codemirror/theme-one-dark'),
			]).then(([editor, lang, oneDark]) => {
				CodeMirror = editor.default;
				markdownLang = lang.markdown;
				theme = oneDark.oneDark;
			});
		}
	});
</script>

<div class="rounded-md border overflow-hidden {className}">
	{#if CodeMirror && markdownLang && theme}
		<CodeMirror
			bind:value
			{placeholder}
			lang={markdownLang()}
			theme={theme}
			styles={{
				'&': {
					minHeight: '120px',
					fontSize: '14px'
				}
			}}
		/>
	{:else}
		<textarea
			class="w-full min-h-[120px] p-3 bg-muted/50 text-sm font-mono resize-y"
			{placeholder}
			readonly
		>{value}</textarea>
	{/if}
</div>
