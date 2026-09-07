import psycopg2
from pgvector.psycopg2 import register_vector

connection_params = {
    "host": "localhost",
    "dbname": "fire",
    "user": "ezekiel",
    "password": "08062006",  # Replace with your actual Postgres password
    "port": 5432
}

try:
    conn = psycopg2.connect(**connection_params)
    cur = conn.cursor()

    register_vector(conn)
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Create temporary table
    cur.execute("CREATE TEMP TABLE cosine_test (id serial PRIMARY KEY, embedding vector(3));")

    # Insert two vectors
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    cur.execute("INSERT INTO cosine_test (embedding) VALUES (%s::vector), (%s::vector);", (v1, v2))

    # Query Cosine Distance with explicit ::vector cast
    query_vec = [1.0, 0.0, 0.0]
    cur.execute("""
        SELECT id, embedding, embedding <=> %s::vector AS cosine_distance 
        FROM cosine_test 
        ORDER BY cosine_distance ASC;
    """, (query_vec,))

    results = cur.fetchall()

    print("--- Cosine Distance Test Results ---")
    for row in results:
        print(f"ID: {row[0]} | Embedding: {row[1]} | Cosine Distance: {row[2]}")

    cur.close()
    conn.close()

except Exception as e:
    print(f"Error testing cosine distance: {e}")