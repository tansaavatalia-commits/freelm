-- Esquema de Supabase para el bot de trading (freelm). Pégalo UNA vez en
-- Supabase > SQL Editor > New query > Run. Se puede repetir sin romper nada.
--
-- Lectura pública de SOLO LECTURA (para el panel); escribir solo puede la
-- secret key / service_role que usa GitHub Actions (salta RLS). Aquí no hay
-- datos personales ni claves: solo capital en papel, señales y aciertos.

create table if not exists public.paper_days (
  day        date primary key,
  equity     double precision not null,
  basket     double precision,
  positions  jsonb default '{}'::jsonb,
  halted     boolean default false,
  updated_at timestamptz default now()
);

create table if not exists public.signals (
  day      date not null,
  variant  text not null,
  symbol   text not null,
  is_long  boolean not null,
  price    double precision,
  primary key (day, variant, symbol)
);

create table if not exists public.scorecard (
  id         text primary key,
  updated_at timestamptz default now(),
  card       jsonb not null
);

alter table public.paper_days enable row level security;
alter table public.signals    enable row level security;
alter table public.scorecard  enable row level security;

drop policy if exists "lectura publica" on public.paper_days;
drop policy if exists "lectura publica" on public.signals;
drop policy if exists "lectura publica" on public.scorecard;
create policy "lectura publica" on public.paper_days for select to anon, authenticated using (true);
create policy "lectura publica" on public.signals    for select to anon, authenticated using (true);
create policy "lectura publica" on public.scorecard  for select to anon, authenticated using (true);
