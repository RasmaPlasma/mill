<script lang="ts">
	import { Select as SelectPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		ref = $bindable(null),
		class: className = undefined,
		placeholder = "",
		...restProps
	}: SelectPrimitive.ValueProps & {
		placeholder?: string;
	} = $props();
</script>

<SelectPrimitive.Value
	bind:ref
	data-slot="select-value"
	class={cn("line-clamp-1 flex items-center gap-1.5", className)}
	{placeholder}
	{...restProps}
/>
