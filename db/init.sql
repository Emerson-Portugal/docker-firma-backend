CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    dni VARCHAR(15) UNIQUE NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE,
    password TEXT NOT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'empleado',
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT NOW()
);

BEGIN;
INSERT INTO usuarios (nombre, dni, email, password, rol) VALUES ('Juan Pérez', '12345678', 'juan.perez@empresa.com', '1234', 'empleado');
INSERT INTO usuarios (nombre, dni, email, password, rol) VALUES ('María López', '87654321', 'maria.lopez@empresa.com', '1234', 'rrhh');
INSERT INTO usuarios (nombre, dni, email, password, rol) VALUES ('Luis Luque', '72797080', 'luizln.lopez@empresa.com', '1234', 'rrhh');
INSERT INTO usuarios (nombre, dni, email, password, rol) VALUES ('Luis Federico', '89431234', 'luizln.lopez2@empresa.com', '1234', 'rrhh');
INSERT INTO usuarios (nombre, dni, email, password, rol) VALUES ('Emerson Portugal', '87654311', 'luizln.lopez3@empresa.com', '1234', 'empleado');
INSERT INTO usuarios (nombre, dni, email, password, rol) VALUES ('Frank Duarte', '22222222', 'luizln.lopez4@empresa.com', '1234', 'rrhh');
INSERT INTO usuarios (nombre, dni, email, password, rol) VALUES ('Papita Gabriela de Duarte', '11111111', 'maldito.lopez@empresa.com', '1234', 'empleado');
INSERT INTO usuarios (nombre, dni, email, password, rol) VALUES ('Splendor', '88888888', 'splendor.lopez@empresa.com', '1234', 'soporte');
COMMIT;

CREATE TABLE IF NOT EXISTS documentos (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nombre_archivo VARCHAR(255) NOT NULL,
    ruta TEXT NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    subido_en TIMESTAMP DEFAULT NOW(),
    firmado_en TIMESTAMP
);

CREATE TABLE IF NOT EXISTS firmas (
    id SERIAL PRIMARY KEY,
    documento_id INT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha TIMESTAMP DEFAULT NOW(),
    ip_origen VARCHAR(45),
    metodo VARCHAR(50) DEFAULT 'web',
    observacion TEXT
);

CREATE INDEX IF NOT EXISTS idx_documentos_usuario ON documentos(usuario_id);
CREATE INDEX IF NOT EXISTS idx_firmas_documento ON firmas(documento_id);
CREATE INDEX IF NOT EXISTS idx_firmas_usuario ON firmas(usuario_id);
