export interface User {
  id: string;
  email: string | null;
  name: string | null;
  picture: string | null;
}

export interface MeResponse {
  authenticated: boolean;
  user: User | null;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used: string | null;
  revoked: boolean;
}

export interface ApiKeyCreated extends ApiKey {
  key: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  weight: number;
  val: number;
  color: string;
  attributes: Record<string, unknown>;
}

export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface Stats {
  events: number;
  nodes: number;
  edges: number;
  memories: number;
  mode: string;
  embedding_provider: string;
}

export interface Interest {
  topic: string;
  weight: number;
}

export interface Profile {
  generated_at: string;
  event_count: number;
  interests: Interest[];
  top_domains: Interest[];
  behavior_types: Record<string, number>;
  decision_patterns: string[];
  recurring_opinions: { text: string; weight: number; last_seen: string }[];
  summary: string;
}

export interface AskResponse {
  question: string;
  answer: string;
  synthesized_by: string;
  sources: { id: string; score: number; text: string; metadata: Record<string, unknown> }[];
  graph_context: { topic: string; weight: number; related: unknown[] }[];
  profile_summary: string;
}

export interface McpConfig {
  brain_url: string;
  api_key_prefix: string | null;
  using_existing_key: boolean;
  config: Record<string, unknown>;
  snippet: string;
  instructions: string;
}

export interface ExtensionUsage {
  events_captured: number;
  nodes: number;
  edges: number;
  memories: number;
  mode: string | null;
  embedding_provider: string | null;
  by_category: Record<string, number>;
  last_sync: string | null;
  active_days: number | null;
}
