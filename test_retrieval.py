from sql_pipeline.retriever import retrieve_tables

def test():
    retrieved = retrieve_tables("registration no 165881", k=5)
    print("\n=== Top 5 Retrieved Tables ===")
    for t in retrieved.keys():
        print(f"- {t}")

if __name__ == "__main__":
    test()
