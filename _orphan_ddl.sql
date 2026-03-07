--
-- PostgreSQL database dump
--

\restrict eJRqmL58bxN1iljru6e2vydzeABbj98GR3A2B9Y2EMe46nlJmzKJzARtJU7EiFR

-- Dumped from database version 16.13 (Debian 16.13-1.pgdg12+1)
-- Dumped by pg_dump version 16.13 (Debian 16.13-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: badge_definitions; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.badge_definitions (
    badge_id text NOT NULL,
    title text NOT NULL,
    description text NOT NULL,
    icon text,
    category text DEFAULT 'general'::text NOT NULL,
    unlock_condition text NOT NULL,
    exp_reward integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.badge_definitions OWNER TO hivemind;

--
-- Name: conductor_dispatches; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.conductor_dispatches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trigger_type character varying(50) NOT NULL,
    trigger_id character varying(200) NOT NULL,
    trigger_detail character varying(500),
    agent_role character varying(50) NOT NULL,
    prompt_type character varying(100),
    execution_mode character varying(20) DEFAULT 'local'::character varying NOT NULL,
    status character varying(20) DEFAULT 'dispatched'::character varying NOT NULL,
    cooldown_key character varying(300),
    result jsonb,
    dispatched_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone
);


ALTER TABLE public.conductor_dispatches OWNER TO hivemind;

--
-- Name: decision_records; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.decision_records (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    epic_id uuid NOT NULL,
    decision_request_id uuid,
    decision text NOT NULL,
    rationale text,
    decided_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.decision_records OWNER TO hivemind;

--
-- Name: decision_requests; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.decision_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    epic_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    backup_owner_id uuid,
    state text DEFAULT 'open'::text NOT NULL,
    sla_due_at timestamp with time zone NOT NULL,
    version integer DEFAULT 0 NOT NULL,
    resolved_by uuid,
    resolved_at timestamp with time zone,
    payload jsonb NOT NULL
);


ALTER TABLE public.decision_requests OWNER TO hivemind;

--
-- Name: epic_node_links; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.epic_node_links (
    epic_id uuid NOT NULL,
    node_id uuid NOT NULL
);


ALTER TABLE public.epic_node_links OWNER TO hivemind;

--
-- Name: epic_restructure_proposals; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.epic_restructure_proposals (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    epic_id uuid NOT NULL,
    proposed_by uuid NOT NULL,
    rationale text NOT NULL,
    proposal text NOT NULL,
    state text DEFAULT 'proposed'::text NOT NULL,
    version integer DEFAULT 0 NOT NULL,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    applied_at timestamp with time zone,
    origin_node_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT valid_restructure_state CHECK ((state = ANY (ARRAY['proposed'::text, 'accepted'::text, 'applied'::text, 'rejected'::text])))
);


ALTER TABLE public.epic_restructure_proposals OWNER TO hivemind;

--
-- Name: exp_events; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.exp_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    event_type text NOT NULL,
    entity_id uuid,
    exp_awarded integer NOT NULL,
    reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.exp_events OWNER TO hivemind;

--
-- Name: mcp_bridge_configs; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.mcp_bridge_configs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(100) NOT NULL,
    namespace character varying(50) NOT NULL,
    transport character varying(20) NOT NULL,
    command character varying(500),
    args jsonb,
    url character varying(500),
    env_vars_encrypted bytea,
    env_vars_nonce bytea,
    enabled boolean DEFAULT true NOT NULL,
    tool_allowlist jsonb,
    tool_blocklist jsonb,
    discovered_tools jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_mcp_bridge_namespace_not_hivemind CHECK (((namespace)::text <> 'hivemind'::text))
);


ALTER TABLE public.mcp_bridge_configs OWNER TO hivemind;

--
-- Name: memory_entries; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.memory_entries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    actor_id uuid NOT NULL,
    agent_role text NOT NULL,
    scope text NOT NULL,
    scope_id uuid,
    session_id uuid NOT NULL,
    content text NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    embedding public.vector(768),
    covered_by uuid,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_entries OWNER TO hivemind;

--
-- Name: memory_facts; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.memory_facts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    entry_id uuid NOT NULL,
    entity text NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    confidence double precision DEFAULT 1.0,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_facts OWNER TO hivemind;

--
-- Name: memory_sessions; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.memory_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    actor_id uuid NOT NULL,
    agent_role text NOT NULL,
    scope text NOT NULL,
    scope_id uuid,
    started_at timestamp with time zone DEFAULT now(),
    ended_at timestamp with time zone,
    entry_count integer DEFAULT 0 NOT NULL,
    compacted boolean DEFAULT false NOT NULL
);


ALTER TABLE public.memory_sessions OWNER TO hivemind;

--
-- Name: memory_summaries; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.memory_summaries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    actor_id uuid NOT NULL,
    agent_role text NOT NULL,
    scope text NOT NULL,
    scope_id uuid,
    session_id uuid,
    content text NOT NULL,
    source_entry_ids uuid[] NOT NULL,
    source_fact_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    source_count integer NOT NULL,
    open_questions text[] DEFAULT '{}'::text[] NOT NULL,
    graduated boolean DEFAULT false NOT NULL,
    graduated_to jsonb,
    embedding public.vector(768),
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_summaries OWNER TO hivemind;

--
-- Name: project_integrations; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.project_integrations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    integration_type character varying(50) NOT NULL,
    github_repo character varying(200),
    github_project_id character varying(100),
    status_field_id character varying(100),
    priority_field_id character varying(100),
    sync_enabled boolean DEFAULT true NOT NULL,
    sync_direction character varying(30) DEFAULT 'bidirectional'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.project_integrations OWNER TO hivemind;

--
-- Name: review_recommendations; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.review_recommendations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    reviewer_dispatch_id uuid,
    recommendation character varying(30) NOT NULL,
    confidence double precision NOT NULL,
    checklist jsonb,
    reasoning text,
    grace_period_until timestamp with time zone,
    auto_approved boolean DEFAULT false NOT NULL,
    vetoed_by uuid,
    vetoed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.review_recommendations OWNER TO hivemind;

--
-- Name: task_node_links; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.task_node_links (
    task_id uuid NOT NULL,
    node_id uuid NOT NULL
);


ALTER TABLE public.task_node_links OWNER TO hivemind;

--
-- Name: user_achievements; Type: TABLE; Schema: public; Owner: hivemind
--

CREATE TABLE public.user_achievements (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    badge_id text NOT NULL,
    earned_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.user_achievements OWNER TO hivemind;

--
-- Name: badge_definitions badge_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.badge_definitions
    ADD CONSTRAINT badge_definitions_pkey PRIMARY KEY (badge_id);


--
-- Name: conductor_dispatches conductor_dispatches_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.conductor_dispatches
    ADD CONSTRAINT conductor_dispatches_pkey PRIMARY KEY (id);


--
-- Name: decision_records decision_records_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_records
    ADD CONSTRAINT decision_records_pkey PRIMARY KEY (id);


--
-- Name: decision_requests decision_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_requests
    ADD CONSTRAINT decision_requests_pkey PRIMARY KEY (id);


--
-- Name: epic_node_links epic_node_links_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.epic_node_links
    ADD CONSTRAINT epic_node_links_pkey PRIMARY KEY (epic_id, node_id);


--
-- Name: epic_restructure_proposals epic_restructure_proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.epic_restructure_proposals
    ADD CONSTRAINT epic_restructure_proposals_pkey PRIMARY KEY (id);


--
-- Name: exp_events exp_events_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.exp_events
    ADD CONSTRAINT exp_events_pkey PRIMARY KEY (id);


--
-- Name: mcp_bridge_configs mcp_bridge_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.mcp_bridge_configs
    ADD CONSTRAINT mcp_bridge_configs_pkey PRIMARY KEY (id);


--
-- Name: memory_entries memory_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_entries
    ADD CONSTRAINT memory_entries_pkey PRIMARY KEY (id);


--
-- Name: memory_facts memory_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT memory_facts_pkey PRIMARY KEY (id);


--
-- Name: memory_sessions memory_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_sessions
    ADD CONSTRAINT memory_sessions_pkey PRIMARY KEY (id);


--
-- Name: memory_summaries memory_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_summaries
    ADD CONSTRAINT memory_summaries_pkey PRIMARY KEY (id);


--
-- Name: project_integrations project_integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.project_integrations
    ADD CONSTRAINT project_integrations_pkey PRIMARY KEY (id);


--
-- Name: review_recommendations review_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.review_recommendations
    ADD CONSTRAINT review_recommendations_pkey PRIMARY KEY (id);


--
-- Name: task_node_links task_node_links_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.task_node_links
    ADD CONSTRAINT task_node_links_pkey PRIMARY KEY (task_id, node_id);


--
-- Name: mcp_bridge_configs uq_mcp_bridge_configs_name; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.mcp_bridge_configs
    ADD CONSTRAINT uq_mcp_bridge_configs_name UNIQUE (name);


--
-- Name: mcp_bridge_configs uq_mcp_bridge_configs_namespace; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.mcp_bridge_configs
    ADD CONSTRAINT uq_mcp_bridge_configs_namespace UNIQUE (namespace);


--
-- Name: project_integrations uq_project_integrations_project_type; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.project_integrations
    ADD CONSTRAINT uq_project_integrations_project_type UNIQUE (project_id, integration_type);


--
-- Name: user_achievements user_achievements_pkey; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.user_achievements
    ADD CONSTRAINT user_achievements_pkey PRIMARY KEY (id);


--
-- Name: user_achievements user_achievements_user_id_badge_id_key; Type: CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.user_achievements
    ADD CONSTRAINT user_achievements_user_id_badge_id_key UNIQUE (user_id, badge_id);


--
-- Name: idx_decision_requests_one_open_per_task; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE UNIQUE INDEX idx_decision_requests_one_open_per_task ON public.decision_requests USING btree (task_id) WHERE (state = 'open'::text);


--
-- Name: idx_decision_requests_sla_due; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_decision_requests_sla_due ON public.decision_requests USING btree (sla_due_at);


--
-- Name: idx_decision_requests_state; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_decision_requests_state ON public.decision_requests USING btree (state);


--
-- Name: idx_decision_requests_task_id; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_decision_requests_task_id ON public.decision_requests USING btree (task_id);


--
-- Name: idx_exp_events_user; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_exp_events_user ON public.exp_events USING btree (user_id, created_at DESC);


--
-- Name: idx_memory_entries_embedding; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_memory_entries_embedding ON public.memory_entries USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_memory_entries_scope; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_memory_entries_scope ON public.memory_entries USING btree (scope, scope_id, created_at DESC);


--
-- Name: idx_memory_entries_uncovered; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_memory_entries_uncovered ON public.memory_entries USING btree (scope, scope_id) WHERE (covered_by IS NULL);


--
-- Name: idx_memory_facts_entity; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_memory_facts_entity ON public.memory_facts USING btree (entity);


--
-- Name: idx_memory_facts_entry; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_memory_facts_entry ON public.memory_facts USING btree (entry_id);


--
-- Name: idx_memory_sessions_scope; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_memory_sessions_scope ON public.memory_sessions USING btree (scope, scope_id, ended_at DESC);


--
-- Name: idx_memory_summaries_embedding; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_memory_summaries_embedding ON public.memory_summaries USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_memory_summaries_scope; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX idx_memory_summaries_scope ON public.memory_summaries USING btree (scope, scope_id, graduated, created_at DESC);


--
-- Name: ix_conductor_dispatches_cooldown; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX ix_conductor_dispatches_cooldown ON public.conductor_dispatches USING btree (cooldown_key) WHERE ((status)::text = 'dispatched'::text);


--
-- Name: ix_conductor_dispatches_role_time; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX ix_conductor_dispatches_role_time ON public.conductor_dispatches USING btree (agent_role, dispatched_at);


--
-- Name: ix_conductor_dispatches_trigger; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX ix_conductor_dispatches_trigger ON public.conductor_dispatches USING btree (trigger_type, trigger_id);


--
-- Name: ix_review_recommendations_grace; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX ix_review_recommendations_grace ON public.review_recommendations USING btree (grace_period_until) WHERE ((auto_approved = false) AND (vetoed_at IS NULL));


--
-- Name: ix_review_recommendations_task_created; Type: INDEX; Schema: public; Owner: hivemind
--

CREATE INDEX ix_review_recommendations_task_created ON public.review_recommendations USING btree (task_id, created_at DESC);


--
-- Name: decision_records decision_records_decided_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_records
    ADD CONSTRAINT decision_records_decided_by_fkey FOREIGN KEY (decided_by) REFERENCES public.users(id);


--
-- Name: decision_records decision_records_decision_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_records
    ADD CONSTRAINT decision_records_decision_request_id_fkey FOREIGN KEY (decision_request_id) REFERENCES public.decision_requests(id);


--
-- Name: decision_records decision_records_epic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_records
    ADD CONSTRAINT decision_records_epic_id_fkey FOREIGN KEY (epic_id) REFERENCES public.epics(id);


--
-- Name: decision_requests decision_requests_backup_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_requests
    ADD CONSTRAINT decision_requests_backup_owner_id_fkey FOREIGN KEY (backup_owner_id) REFERENCES public.users(id);


--
-- Name: decision_requests decision_requests_epic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_requests
    ADD CONSTRAINT decision_requests_epic_id_fkey FOREIGN KEY (epic_id) REFERENCES public.epics(id);


--
-- Name: decision_requests decision_requests_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_requests
    ADD CONSTRAINT decision_requests_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id);


--
-- Name: decision_requests decision_requests_resolved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_requests
    ADD CONSTRAINT decision_requests_resolved_by_fkey FOREIGN KEY (resolved_by) REFERENCES public.users(id);


--
-- Name: decision_requests decision_requests_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.decision_requests
    ADD CONSTRAINT decision_requests_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: epic_node_links epic_node_links_epic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.epic_node_links
    ADD CONSTRAINT epic_node_links_epic_id_fkey FOREIGN KEY (epic_id) REFERENCES public.epics(id);


--
-- Name: epic_node_links epic_node_links_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.epic_node_links
    ADD CONSTRAINT epic_node_links_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.code_nodes(id);


--
-- Name: epic_restructure_proposals epic_restructure_proposals_epic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.epic_restructure_proposals
    ADD CONSTRAINT epic_restructure_proposals_epic_id_fkey FOREIGN KEY (epic_id) REFERENCES public.epics(id);


--
-- Name: epic_restructure_proposals epic_restructure_proposals_origin_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.epic_restructure_proposals
    ADD CONSTRAINT epic_restructure_proposals_origin_node_id_fkey FOREIGN KEY (origin_node_id) REFERENCES public.nodes(id);


--
-- Name: epic_restructure_proposals epic_restructure_proposals_proposed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.epic_restructure_proposals
    ADD CONSTRAINT epic_restructure_proposals_proposed_by_fkey FOREIGN KEY (proposed_by) REFERENCES public.users(id);


--
-- Name: epic_restructure_proposals epic_restructure_proposals_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.epic_restructure_proposals
    ADD CONSTRAINT epic_restructure_proposals_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: exp_events exp_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.exp_events
    ADD CONSTRAINT exp_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: memory_entries memory_entries_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_entries
    ADD CONSTRAINT memory_entries_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: memory_entries memory_entries_covered_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_entries
    ADD CONSTRAINT memory_entries_covered_by_fkey FOREIGN KEY (covered_by) REFERENCES public.memory_summaries(id);


--
-- Name: memory_entries memory_entries_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_entries
    ADD CONSTRAINT memory_entries_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.memory_sessions(id);


--
-- Name: memory_facts memory_facts_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT memory_facts_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.memory_entries(id);


--
-- Name: memory_sessions memory_sessions_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_sessions
    ADD CONSTRAINT memory_sessions_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: memory_summaries memory_summaries_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_summaries
    ADD CONSTRAINT memory_summaries_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: memory_summaries memory_summaries_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.memory_summaries
    ADD CONSTRAINT memory_summaries_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.memory_sessions(id);


--
-- Name: project_integrations project_integrations_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.project_integrations
    ADD CONSTRAINT project_integrations_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: review_recommendations review_recommendations_reviewer_dispatch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.review_recommendations
    ADD CONSTRAINT review_recommendations_reviewer_dispatch_id_fkey FOREIGN KEY (reviewer_dispatch_id) REFERENCES public.conductor_dispatches(id) ON DELETE SET NULL;


--
-- Name: review_recommendations review_recommendations_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.review_recommendations
    ADD CONSTRAINT review_recommendations_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE CASCADE;


--
-- Name: review_recommendations review_recommendations_vetoed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.review_recommendations
    ADD CONSTRAINT review_recommendations_vetoed_by_fkey FOREIGN KEY (vetoed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: task_node_links task_node_links_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.task_node_links
    ADD CONSTRAINT task_node_links_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.code_nodes(id);


--
-- Name: task_node_links task_node_links_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.task_node_links
    ADD CONSTRAINT task_node_links_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: user_achievements user_achievements_badge_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.user_achievements
    ADD CONSTRAINT user_achievements_badge_id_fkey FOREIGN KEY (badge_id) REFERENCES public.badge_definitions(badge_id);


--
-- Name: user_achievements user_achievements_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hivemind
--

ALTER TABLE ONLY public.user_achievements
    ADD CONSTRAINT user_achievements_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict eJRqmL58bxN1iljru6e2vydzeABbj98GR3A2B9Y2EMe46nlJmzKJzARtJU7EiFR

