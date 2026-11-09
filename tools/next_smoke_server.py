from pathlib import Path
import uvicorn
from viewer_next.server import create_app

app=create_app(Path('work/next-smoke-state'),'smoke-token')
app.state.store.add(Path('examples-v2').resolve())
if __name__=='__main__':
    uvicorn.run(app,host='127.0.0.1',port=8879)
