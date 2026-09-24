CREATE TABLE departments (
    id INTEGER PRIMARY KEY,
    manager_id INTEGER REFERENCES employees (id)
);
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    department_id INTEGER REFERENCES departments (id)
);
