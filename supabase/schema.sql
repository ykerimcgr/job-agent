-- Run this file once in the Supabase SQL Editor for each candidate's project.
-- The GitHub Actions job must use a server-side Supabase secret/service-role key.

create table if not exists public.profile_cache (
    cv_hash text primary key,
    profile_json jsonb not null,
    updated_at timestamptz not null default now()
);

create table if not exists public.job_cache (
    job_hash text primary key,
    parsed_job_json jsonb,
    score_result_json jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.emailed_jobs (
    job_hash text primary key,
    sent_at timestamptz not null default now(),
    location text not null default 'UK',
    company text not null default '',
    title text not null default '',
    url text not null default '',
    score numeric not null default 0
);

-- Upgrade installations that were created before this tracked schema existed.
alter table public.emailed_jobs
    add column if not exists location text not null default 'UK';

create index if not exists profile_cache_updated_at_idx
    on public.profile_cache (updated_at desc);

create index if not exists job_cache_updated_at_idx
    on public.job_cache (updated_at desc);

create index if not exists emailed_jobs_sent_at_idx
    on public.emailed_jobs (sent_at desc);

alter table public.profile_cache enable row level security;
alter table public.job_cache enable row level security;
alter table public.emailed_jobs enable row level security;

revoke all on table public.profile_cache from anon, authenticated;
revoke all on table public.job_cache from anon, authenticated;
revoke all on table public.emailed_jobs from anon, authenticated;

grant select, insert, update, delete on table public.profile_cache to service_role;
grant select, insert, update, delete on table public.job_cache to service_role;
grant select, insert, update, delete on table public.emailed_jobs to service_role;
