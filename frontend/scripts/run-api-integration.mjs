import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdtemp, rm } from 'node:fs/promises'
import { createServer } from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendDirectory = path.resolve(scriptDirectory, '..')
const projectRoot = path.resolve(frontendDirectory, '..')
const frontendOrigin = 'http://localhost:5173'

function reservePort() {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close((error) => (error ? reject(error) : resolve(port)))
    })
  })
}

function waitForExit(child) {
  return new Promise((resolve, reject) => {
    child.once('error', reject)
    child.once('exit', (code, signal) => resolve({ code, signal }))
  })
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

async function waitForApi(child, exitPromise, healthUrl) {
  const deadline = Date.now() + 20_000
  while (Date.now() < deadline) {
    const exitState = await Promise.race([
      exitPromise.then((result) => ({ result }), (error) => ({ error })),
      delay(100).then(() => null),
    ])
    if (exitState) {
      if (exitState.error) throw exitState.error
      throw new Error(`A API de integração terminou antes de ficar pronta (código ${exitState.result.code}).`)
    }

    try {
      const response = await fetch(healthUrl)
      if (response.ok && (await response.json()).status === 'ready') return
    } catch {
      // A API ainda pode estar iniciando; a próxima tentativa é limitada pelo prazo acima.
    }
  }
  child.kill()
  throw new Error('A API de integração não ficou pronta em 20 segundos.')
}

async function stopChild(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return
  const exited = waitForExit(child).catch(() => undefined)
  child.kill()
  await Promise.race([exited, delay(3_000)])
}

async function main() {
  const projectPython = process.platform === 'win32'
    ? path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
    : path.join(projectRoot, '.venv', 'bin', 'python')
  const pythonCommand = process.env.PYTHON
    || (existsSync(projectPython) ? projectPython : null)
  if (!pythonCommand) {
    throw new Error(
      'Configure PYTHON ou crie o ambiente virtual .venv do projeto para executar a API de integração.',
    )
  }

  const apiPort = await reservePort()
  const testDataDirectory = await mkdtemp(path.join(projectRoot, '.tmp-api-integration-'))
  const apiUrl = `http://127.0.0.1:${apiPort}`
  const pythonPath = [
    path.join(projectRoot, 'backend'),
    process.env.PYTHONPATH,
  ].filter(Boolean).join(path.delimiter)

  let apiProcess
  let vitestProcess
  try {
    apiProcess = spawn(pythonCommand, [
      '-m', 'uvicorn', 'api_app:app',
      '--app-dir', path.join(projectRoot, 'tests', 'integration'),
      '--host', '127.0.0.1',
      '--port', String(apiPort),
      '--log-level', 'warning',
    ], {
      cwd: projectRoot,
      env: {
        ...process.env,
        PYTHONPATH: pythonPath,
        SENTINELA_PREFERENCES_DIR: testDataDirectory,
        INTEGRATION_FRONTEND_ORIGIN: frontendOrigin,
      },
      stdio: 'inherit',
    })
    const apiExit = waitForExit(apiProcess)
    await waitForApi(apiProcess, apiExit, `${apiUrl}/__test__/health`)

    const vitestCli = path.join(frontendDirectory, 'node_modules', 'vitest', 'vitest.mjs')
    vitestProcess = spawn(process.execPath, [
      vitestCli,
      'run',
      '--config', path.join(frontendDirectory, 'vitest.integration.config.js'),
    ], {
      cwd: frontendDirectory,
      env: {
        ...process.env,
        VITE_API_URL: apiUrl,
      },
      stdio: 'inherit',
    })
    const result = await waitForExit(vitestProcess)
    if (result.code !== 0) {
      throw new Error(`Os testes de integração terminaram com código ${result.code ?? result.signal}.`)
    }
  } finally {
    await stopChild(vitestProcess)
    await stopChild(apiProcess)
    await rm(testDataDirectory, { recursive: true, force: true })
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
