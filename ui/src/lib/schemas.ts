import { z } from 'zod/v3';

export const agentCreateSchema = z.object({
	name: z.string().min(1, 'Name is required').max(255),
	model_id: z.string().min(1, 'Please select a model'),
	system_prompt: z.string().default(''),
	description: z.string().default(''),
	tools: z.string().optional(),
	mcp_servers_json: z.string().optional(),
	metadata_json: z.string().optional(),
});

export const agentUpdateSchema = z.object({
	name: z.string().min(1).max(255).optional(),
	model_id: z.string().optional(),
	system_prompt: z.string().default(''),
	description: z.string().default(''),
	tools: z.string().optional(),
	mcp_servers_json: z.string().optional(),
	metadata_json: z.string().optional(),
}).refine(
	(data) => Object.keys(data).length > 0,
	{ message: 'At least one field must be provided' }
);

export const sessionEventSchema = z.object({
	message: z.string().min(1, 'Message cannot be empty'),
});

export const sessionCreateSchema = z.object({
	agent_id: z.string().min(1, 'Agent is required'),
	environment_id: z.string().min(1, 'Environment is required'),
	vault_ids: z.string().optional(),
	title: z.string().optional(),
	repositories_json: z.string().optional(),
	skill_repos_json: z.string().optional(),
});

export const vaultCreateSchema = z.object({
	display_name: z.string().min(1, 'Display name is required').max(255),
	metadata_json: z.string().optional(),
});

export const credentialCreateSchema = z.object({
	display_name: z.string().min(1),
	mcp_server_url: z.string().url('Must be a valid URL'),
	auth_type: z.enum(['mcp_oauth', 'static_bearer']),
	token: z.string().min(1, 'Token is required'),
	refresh_token: z.string().optional(),
	token_endpoint: z.string().url().optional().or(z.literal('')),
	client_id: z.string().optional(),
	scope: z.string().optional(),
	expires_at: z.string().optional(),
});

export const credentialRotateSchema = z.object({
	credential_id: z.string(),
	token: z.string().min(1),
	refresh_token: z.string().optional(),
	expires_at: z.string().optional(),
});

export const modelCreateSchema = z.object({
	display_name: z.string().min(1, 'Display name is required').max(255),
	provider: z.string().min(1, 'Provider is required').max(255),
	provider_model: z.string().min(1, 'Provider model ID is required').max(255),
	description: z.string().default(''),
});

export const modelUpdateSchema = z.object({
	display_name: z.string().min(1).max(255).optional(),
	provider: z.string().min(1).max(255).optional(),
	provider_model: z.string().min(1).max(255).optional(),
	description: z.string().default(''),
}).refine(
	(data) => Object.keys(data).length > 0,
	{ message: 'At least one field must be provided' }
);

export const secretUpsertSchema = z.object({
	name: z.string().min(1).max(255),
	value: z.string().min(1, 'Value is required'),
	scope: z.string().default('global'),
	description: z.string().default(''),
});

export const environmentSkillRepoSchema = z.object({
	repo: z.string().min(1, 'Repo URL is required'),
	skill_name: z.string().default('*'),
});

export const environmentCreateSchema = z.object({
	name: z.string().min(1, 'Name is required').max(255),
	base_image: z.string().optional(),
	packages_pip: z.string().optional(),
	packages_npm: z.string().optional(),
	packages_apt: z.string().optional(),
	networking_type: z.enum(['limited', 'open']).default('limited'),
	networking_allowed_hosts: z.string().optional(),
	networking_allow_package_managers: z.boolean().default(false),
	resource_memory: z.string().default('1g'),
	resource_cpus: z.coerce.number().default(1),
	resource_pids_limit: z.coerce.number().int().default(256),
	skill_repos_json: z.string().optional(),
	repositories_json: z.string().optional(),
});

export const environmentUpdateSchema = z.object({
	name: z.string().min(1).max(255).optional(),
	base_image: z.string().optional(),
	packages_pip: z.string().optional(),
	packages_npm: z.string().optional(),
	packages_apt: z.string().optional(),
	networking_type: z.enum(['limited', 'open']).optional(),
	networking_allowed_hosts: z.string().optional(),
	networking_allow_package_managers: z.boolean().optional(),
	resource_memory: z.string().optional(),
	resource_cpus: z.coerce.number().optional(),
	resource_pids_limit: z.coerce.number().int().optional(),
	skill_repos_json: z.string().optional(),
	repositories_json: z.string().optional(),
}).refine(
	(data) => Object.keys(data).length > 0,
	{ message: 'At least one field must be provided' }
);
