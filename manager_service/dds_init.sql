create table if not exists jobs (
    job_id serial primary key,
    status varchar(20) default 'submitted',
    input_files varchar(255),
    output_path varchar(255),
    mapper_code varchar(255),
    reducer_code varchar(255),
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    user_id integer not null
);

create table if not exists workers (
    worker_id serial primary key,
    pod_name varchar(20),
    status varchar(20) default 'idle',
    last_sign timestamptz default now()
);

create table if not exists tasks (
    task_id serial primary key,
    type varchar(10),
    status varchar(20) default 'idle',
    input_split varchar(255),
    data_location varchar(255),
    job_id integer not null,
    worker_id integer,
    foreign key (job_id) references jobs(job_id) on delete cascade,
    foreign key (worker_id) references workers(worker_id) on delete set null
);