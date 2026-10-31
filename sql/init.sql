

CREATE TABLE public.task_pnt (
	loc varchar NOT NULL,
	batch varchar NOT NULL,
	files smallint NOT NULL,
	status smallint NOT NULL,
	CONSTRAINT task_pnt_pk PRIMARY KEY (loc)
);



