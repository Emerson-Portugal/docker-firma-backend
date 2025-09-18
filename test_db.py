from app.database import get_connection

def test_connection():
    print("Probando conexión a la base de datos...")
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # 1. Verificar si la tabla usuarios existe
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'usuarios'
                );
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                print("¡Error! La tabla 'usuarios' no existe en la base de datos.")
                return
                
            # 2. Obtener la estructura de la tabla usuarios
            cursor.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'usuarios' 
                ORDER BY ordinal_position;
            """)
            
            print("\nEstructura de la tabla 'usuarios':")
            print("-" * 50)
            print(f"{'Columna':<20} {'Tipo':<20} ¿Nulo?")
            print("-" * 50)
            for col in cursor.fetchall():
                print(f"{col[0]:<20} {col[1]:<20} {col[2]}")
            
            # 3. Verificar si hay datos en la tabla
            cursor.execute("SELECT COUNT(*) FROM usuarios;")
            count = cursor.fetchone()[0]
            print(f"\nTotal de registros en 'usuarios': {count}")
            
        except Exception as e:
            print(f"Error al ejecutar la consulta: {e}")
        finally:
            if conn:
                conn.close()
                print("\nConexión cerrada correctamente")
    else:
        print("No se pudo establecer la conexión a la base de datos")

if __name__ == "__main__":
    test_connection()
