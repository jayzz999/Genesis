import asyncio
from backend.genesis.runtime import _tool_decompose_goal
from backend.genesis import store

async def main():
    org = store.load_organism("o_71f0cea266f7")
    print("Before:", len(org.sub_goals))
    res = await _tool_decompose_goal([{"goal": "Test goal 1"}, {"goal": "Test goal 2"}], "o_71f0cea266f7")
    print("Result:", res)
    org = store.load_organism("o_71f0cea266f7")
    print("After:", len(org.sub_goals))

asyncio.run(main())
