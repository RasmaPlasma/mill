<script lang="ts">
	import { FileCode } from 'lucide-svelte';
	import Prism from 'prismjs';
	import 'prismjs/components/prism-json';
	import 'prismjs/components/prism-python';
	import 'prismjs/components/prism-bash';
	import 'prismjs/components/prism-typescript';
	import 'prismjs/components/prism-javascript';
	import 'prismjs/components/prism-css';
	import 'prismjs/components/prism-yaml';
	import 'prismjs/components/prism-markdown';
	import 'prismjs/components/prism-rust';
	import 'prismjs/components/prism-go';
	import 'prismjs/components/prism-java';
	import 'prismjs/components/prism-c';
	import 'prismjs/components/prism-cpp';
	import 'prismjs/components/prism-sql';

	let { filePath = '', content = '' }: { filePath?: string; content?: string } = $props();

	function getLangFromPath(path: string): string | null {
		const ext = path.split('.').pop()?.toLowerCase() || '';
		const map: Record<string, string> = {
			py: 'python',
			js: 'javascript',
			ts: 'typescript',
			json: 'json',
			css: 'css',
			html: 'markup',
			yml: 'yaml',
			yaml: 'yaml',
			sql: 'sql',
			rs: 'rust',
			go: 'go',
			java: 'java',
			c: 'c',
			cpp: 'cpp',
			cc: 'cpp',
			md: 'markdown',
			sh: 'bash',
			bash: 'bash',
			zsh: 'bash',
		};
		return map[ext] || null;
	}

	function highlightContent(text: string, lang: string | null): string {
		if (!lang || !Prism.languages[lang]) {
			return text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
		}
		return Prism.highlight(text, Prism.languages[lang], lang);
	}

	const lang = $derived(getLangFromPath(filePath));
	const highlighted = $derived(highlightContent(content, lang));
</script>

<div class="rounded border bg-muted/30 overflow-hidden">
	<div class="flex items-center gap-2 px-2.5 py-1.5 border-b bg-muted/50">
		<FileCode class="h-3.5 w-3.5 text-muted-foreground" />
		<span class="text-[10px] font-medium text-muted-foreground font-mono truncate">{filePath}</span>
		{#if lang}
			<span class="text-[10px] text-muted-foreground ml-auto uppercase">{lang}</span>
		{/if}
	</div>
	<pre class="px-3 py-2 text-xs font-mono leading-relaxed overflow-x-auto max-h-[400px]"><code>{@html highlighted}</code></pre>
</div>
