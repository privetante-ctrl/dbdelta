CREATE TABLE departments (
    id integer PRIMARY KEY,
    manager_id integer
);
CREATE TABLE employees (
    id integer PRIMARY KEY,
    department_id integer REFERENCES departments (id)
);
ALTER TABLE departments
    ADD CONSTRAINT departments_manager_fkey FOREIGN KEY (manager_id) REFERENCES employees (id);
