--
-- PostgreSQL database dump
--

\restrict iJq2PyA1nfimjHM0UpJQ8eFFmp1eAuON5GQnDasmu3KLz5KwHyQ1Te7A0T40y5g

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

--
-- Data for Name: badge_definitions; Type: TABLE DATA; Schema: public; Owner: hivemind
--

COPY public.badge_definitions (badge_id, title, description, icon, category, unlock_condition, exp_reward, created_at) FROM stdin;
fog_clearer	Fog Clearer	500 Code-Nodes im Nexus Grid erkundet	🗺️	exploration	code_nodes_explored >= 500	200	2026-03-04 13:54:12.836246+00
guild_contributor	Guild Contributor	10 eigene Skills von Peers übernommen	⚔️	collaboration	skills_forked_by_peers >= 10	150	2026-03-04 13:54:12.836246+00
master_architect	Master Architect	20 Epics erfolgreich abgeschlossen	🏗️	quality	epics_completed >= 20	300	2026-03-04 13:54:12.836246+00
sla_savior	SLA Savior	10 Eskalationen innerhalb SLA gelöst	⏱️	quality	escalations_resolved_in_sla >= 10	100	2026-03-04 13:54:12.836246+00
first_blood	First Blood	Ersten Task abgeschlossen	🎯	general	tasks_completed >= 1	25	2026-03-04 13:54:12.836246+00
cartographer	Cartographer	1000 Code-Nodes kartiert	🌍	exploration	code_nodes_explored >= 1000	500	2026-03-04 13:54:12.836246+00
skill_smith	Skill Smith	10 Skill-Proposals gemergt	🔧	quality	skills_merged >= 10	200	2026-03-04 13:54:12.836246+00
\.


--
-- Data for Name: decision_records; Type: TABLE DATA; Schema: public; Owner: hivemind
--

COPY public.decision_records (id, epic_id, decision_request_id, decision, rationale, decided_by, created_at) FROM stdin;
b9658640-e18a-4039-bb9d-0045b65f435c	a3e5cd81-ed19-4895-81a0-ac3f7fe4356e	\N	Separate Outbox-Consumer pro Direction statt einem generischen Consumer	Phase F hat bewiesen dass peer_outbound seinen eigenen Consumer braucht (Ed25519-Signing, Hub-Relay-Fallback). Phase 7 ergänzt einen outbound-Consumer mit System-spezifischen Adaptern (YouTrack, Sentry). Ein generischer Consumer wäre zu komplex — jeder Direction-Typ hat eigene Auth, Retry- und Delivery-Logik. Drei separate Jobs: peer_outbound (Phase F), outbound (Phase 7), inbound-routing (Phase 7).	34a71989-e59a-4719-b423-2111cbfa6298	2026-03-04 13:57:09.874637+00
6ff3cee3-c717-4e94-8866-182f17888ee1	a3e5cd81-ed19-4895-81a0-ac3f7fe4356e	\N	pgvector Cosine-Similarity mit konfigurierbarem Threshold (Default 0.85) für Auto-Routing	Alternative war regelbasiertes Routing (Keyword-Matching). pgvector-Similarity ist flexibler, braucht keine manuellen Regeln und nutzt die seit Phase 3 vorhandene Embedding-Infrastruktur. Threshold ist per API änderbar ohne Neustart. Bei Embedding-Service-Ausfall: Graceful Degradation zu [UNROUTED] statt Fehlschlag.	34a71989-e59a-4719-b423-2111cbfa6298	2026-03-04 13:57:09.874637+00
2be574e4-5a47-46fe-81ff-5636773e8957	a3e5cd81-ed19-4895-81a0-ac3f7fe4356e	\N	DLQ-Requeue setzt attempts auf 0 (frischer Retry-Zyklus) statt Weiterzählen	Ein Requeue ist eine bewusste Admin-Aktion (z.B. nach Bug-Fix oder Netzwerk-Recovery). Weiterzählen der attempts würde den Eintrag sofort wieder in die DLQ schieben wenn der erste Retry fehlschlägt. Reset auf 0 gibt dem Eintrag einen vollständigen frischen Zyklus (5 Versuche mit Exponential Backoff).	34a71989-e59a-4719-b423-2111cbfa6298	2026-03-04 13:57:09.874637+00
\.


--
-- PostgreSQL database dump complete
--

\unrestrict iJq2PyA1nfimjHM0UpJQ8eFFmp1eAuON5GQnDasmu3KLz5KwHyQ1Te7A0T40y5g

