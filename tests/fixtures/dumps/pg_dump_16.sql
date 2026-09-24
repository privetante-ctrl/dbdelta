--
-- PostgreSQL database dump
--

\restrict lafdrSUfORULm5dBwhB1WLczTDKop8mVsmYpabJM6PdfcQ7uJR5CqedkAbHZdc0

-- Dumped from database version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

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
-- Name: dumped; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA dumped;


--
-- Name: mood; Type: TYPE; Schema: dumped; Owner: -
--

CREATE TYPE dumped.mood AS ENUM (
    'sad',
    'ok'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: orgs; Type: TABLE; Schema: dumped; Owner: -
--

CREATE TABLE dumped.orgs (
    id integer NOT NULL,
    code character varying(10) NOT NULL
);


--
-- Name: orgs_id_seq; Type: SEQUENCE; Schema: dumped; Owner: -
--

CREATE SEQUENCE dumped.orgs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: orgs_id_seq; Type: SEQUENCE OWNED BY; Schema: dumped; Owner: -
--

ALTER SEQUENCE dumped.orgs_id_seq OWNED BY dumped.orgs.id;


--
-- Name: users; Type: TABLE; Schema: dumped; Owner: -
--

CREATE TABLE dumped.users (
    id bigint NOT NULL,
    email text NOT NULL,
    org_id integer,
    m dumped.mood DEFAULT 'ok'::dumped.mood,
    price numeric(10,2),
    status character varying(5),
    CONSTRAINT users_price_check CHECK ((price > (0)::numeric)),
    CONSTRAINT users_status_check CHECK (((status)::text = ANY ((ARRAY['a'::character varying, 'b'::character varying])::text[])))
);


--
-- Name: TABLE users; Type: COMMENT; Schema: dumped; Owner: -
--

COMMENT ON TABLE dumped.users IS 'people';


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: dumped; Owner: -
--

ALTER TABLE dumped.users ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dumped.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: v; Type: VIEW; Schema: dumped; Owner: -
--

CREATE VIEW dumped.v AS
 SELECT id
   FROM dumped.users;


--
-- Name: orgs id; Type: DEFAULT; Schema: dumped; Owner: -
--

ALTER TABLE ONLY dumped.orgs ALTER COLUMN id SET DEFAULT nextval('dumped.orgs_id_seq'::regclass);


--
-- Name: orgs orgs_code_key; Type: CONSTRAINT; Schema: dumped; Owner: -
--

ALTER TABLE ONLY dumped.orgs
    ADD CONSTRAINT orgs_code_key UNIQUE (code);


--
-- Name: orgs orgs_pkey; Type: CONSTRAINT; Schema: dumped; Owner: -
--

ALTER TABLE ONLY dumped.orgs
    ADD CONSTRAINT orgs_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: dumped; Owner: -
--

ALTER TABLE ONLY dumped.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ux_email; Type: INDEX; Schema: dumped; Owner: -
--

CREATE UNIQUE INDEX ux_email ON dumped.users USING btree (lower(email)) WHERE ((status)::text = 'a'::text);


--
-- Name: users users_org_id_fkey; Type: FK CONSTRAINT; Schema: dumped; Owner: -
--

ALTER TABLE ONLY dumped.users
    ADD CONSTRAINT users_org_id_fkey FOREIGN KEY (org_id) REFERENCES dumped.orgs(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict lafdrSUfORULm5dBwhB1WLczTDKop8mVsmYpabJM6PdfcQ7uJR5CqedkAbHZdc0
