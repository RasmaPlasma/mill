<script lang="ts">
	import { onMount } from 'svelte';
	import { marked } from 'marked';
	import Prism from 'prismjs';
	import 'prismjs/components/prism-json';
	import 'prismjs/components/prism-python';
	import 'prismjs/components/prism-bash';
	import 'prismjs/components/prism-typescript';
	import 'prismjs/components/prism-javascript';
	import 'prismjs/components/prism-css';
	import 'prismjs/components/prism-yaml';
	import 'prismjs/components/prism-sql';
	import 'prismjs/components/prism-rust';
	import 'prismjs/components/prism-go';
	import 'prismjs/components/prism-java';
	import 'prismjs/components/prism-c';
	import 'prismjs/components/prism-cpp';
	import 'prismjs/components/prism-markdown';

	let { content = '', variant = 'agent' } = $props<{
		content?: string;
		variant?: 'agent' | 'user' | 'thinking';
	}>();

	let html = $state('');

	const VARIANT_STYLES: Record<string, string> = {
		agent: 'border-l-2 border-blue-500/30 bg-blue-500/5',
		user: 'border-l-2 border-pink-500/30 bg-pink-500/5',
		thinking: 'border-l-2 border-purple-500/30 bg-purple-500/5',
	};

	function getPrismLang(lang: string): string | null {
		const map: Record<string, string> = {
			py: 'python',
			python: 'python',
			sh: 'bash',
			bash: 'bash',
			shell: 'bash',
			zsh: 'bash',
			js: 'javascript',
			javascript: 'javascript',
			ts: 'typescript',
			typescript: 'typescript',
			json: 'json',
			css: 'css',
			html: 'markup',
			xml: 'markup',
			yaml: 'yaml',
			yml: 'yaml',
			sql: 'sql',
			rs: 'rust',
			rust: 'rust',
			go: 'go',
			java: 'java',
			c: 'c',
			cpp: 'cpp',
			'c++': 'cpp',
			md: 'markdown',
			markdown: 'markdown',
		};
		return map[lang?.toLowerCase()] || null;
	}

	$effect(() => {
		const currentContent = content;
		if (!currentContent) {
			html = '';
			return;
		}

		// Configure marked with custom code block renderer
		const renderer = new marked.Renderer();
		renderer.code = ({ text, lang }: { text: string; lang?: string }) => {
			const prismLang = getPrismLang(lang || '');
			if (prismLang && Prism.languages[prismLang]) {
				const highlighted = Prism.highlight(text, Prism.languages[prismLang], prismLang);
				return `<pre class="language-${prismLang}"><code class="language-${prismLang}">${highlighted}</code></pre>`;
			}
			return `<pre><code>${text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>`;
		};

		(async () => {
			const parsed = await marked.parse(currentContent, {
				breaks: true,
				renderer,
			});

			// Sanitize with DOMPurify (browser only)
			let safeHtml = parsed;
			if (typeof window !== 'undefined') {
				const DOMPurify = (await import('dompurify')).default;
				safeHtml = DOMPurify.sanitize(parsed, {
					ALLOWED_TAGS: [
						'p', 'br', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li',
						'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
						'blockquote', 'a', 'hr', 'div', 'span',
					],
					ALLOWED_ATTR: ['href', 'class', 'title'],
				});
			}

			html = safeHtml;
		})();
	});
</script>

<div class="text-sm leading-relaxed {VARIANT_STYLES[variant]} rounded-r px-3 py-2">
	{#if html}
		<div class="prose prose-sm max-w-none dark:prose-invert">
			{@html html}
		</div>
	{:else}
		<div class="text-muted-foreground text-xs">Loading...</div>
	{/if}
</div>

<style>
	:global(.prose pre) {
		background: hsl(var(--muted));
		padding: 0.75rem;
		border-radius: 0.375rem;
		overflow-x: auto;
		font-size: 0.75rem;
		line-height: 1.5;
		margin: 0.5rem 0;
	}
	:global(.prose code) {
		background: hsl(var(--muted));
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
		font-size: 0.75rem;
		font-family: ui-monospace, monospace;
	}
	:global(.prose pre code) {
		background: transparent;
		padding: 0;
		border-radius: 0;
	}
	:global(.prose p) {
		margin: 0.5rem 0;
	}
	:global(.prose h1, .prose h2, .prose h3, .prose h4) {
		margin: 0.75rem 0 0.5rem;
		font-weight: 600;
	}
	:global(.prose ul, .prose ol) {
		margin: 0.5rem 0;
		padding-left: 1.25rem;
	}
	:global(.prose blockquote) {
		border-left: 2px solid hsl(var(--border));
		padding-left: 0.75rem;
		margin: 0.5rem 0;
		color: hsl(var(--muted-foreground));
	}
</style>
