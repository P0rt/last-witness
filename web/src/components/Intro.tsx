import type { Meta } from "../types";

export default function Intro({ meta, onStart }: { meta: Meta; onStart: () => void }) {
  const m = meta.meta;
  return (
    <div className="intro">
      <div className="intro-card">
        <p className="mono dim">RECOVERED MEDIA · DAT24 · “BEACON FULL 17-OCT-99”</p>
        <h1>October 1999.<br />The Lighthouse Network went offline.</h1>
        <p>
          It was a small community of radio listeners on the Oregon coast. They logged numbers stations,
          dead beacons and carriers with no name. Then, in one weekend, almost everything they wrote disappeared.
        </p>
        <p>
          Twenty-seven years later a damaged backup tape turned up at a surplus auction.
          <b> {m.recovered} of {m.originals} files</b> could be read. The rest is gone, or exists only as a broken link.
        </p>
        <p>
          You will work with an investigator: <span className="mono">{meta.model}</span>, an open-weight model running
          locally. It has never been told what happened. It sees only the documents you open, and every claim it
          makes has to quote them. You can object to any claim.
        </p>
        <p>When you think you know, fill in the reconstruction and press <b>Reveal</b>. Then you will find out which of
          its conclusions were real, and which were ghosts.</p>
        <button className="primary" onClick={onStart}>Mount the tape</button>
        <p className="tagline">The internet forgets. The evidence doesn’t.</p>
      </div>
    </div>
  );
}
