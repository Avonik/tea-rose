import { Link } from 'react-router-dom'
import { IconChevron } from '../components/icons'
import { Page } from '../motion/Reveal'

export default function NotFoundPage() {
  return (
    <Page className="band notfound">
      <div className="wrap notfound__inner">
        <p className="eyebrow">404</p>
        <h1 className="t-display">This page does not exist.</h1>
        <p className="t-subtitle">The link may be mistyped, or the run may have expired.</p>
        <p>
          <Link className="btn btn--link btn--lg" to="/">
            Back to cases <IconChevron size={14} />
          </Link>
        </p>
      </div>
    </Page>
  )
}
