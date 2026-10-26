import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api'
import { ErrorState, StateView } from '../components/ui'
import { useLiveRun } from '../lib/useLiveRun'
import RunView from '../run/RunView'

export default function RunPage() {
  const { id = '' } = useParams()
  const run = useLiveRun(id)

  if (run.loading) return <StateView kind="loading" title="Opening the run" />
  if (run.error && !run.result) {
    const ae = run.error instanceof ApiError ? run.error : null
    if (ae?.status === 401)
      return (
        <StateView
          kind="error"
          title="Your session has ended"
          body="Live runs are tied to your passcode session. Unlock live mode again to view this run."
          action={
            <Link className="btn btn--sm" to="/analyze">
              Go to Analyze
            </Link>
          }
        />
      )
    if (ae?.status === 404)
      return (
        <StateView
          kind="empty"
          title="Run not found"
          body="This run does not exist or has expired."
          action={
            <Link className="btn btn--sm" to="/analyze">
              Start a new analysis
            </Link>
          }
        />
      )
    return <ErrorState error={run.error} onRetry={() => window.location.reload()} title="Could not open this run" />
  }
  if (!run.result) return null

  return (
    <RunView
      result={run.result}
      events={run.events}
      live
      streaming={run.streaming}
      connection={run.connection}
      onFollowup={run.followup}
      onReconnect={run.reconnect}
    />
  )
}
