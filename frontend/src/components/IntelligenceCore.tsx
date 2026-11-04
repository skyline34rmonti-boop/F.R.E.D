import { motion, useReducedMotion } from 'framer-motion';
export type CoreState = 'idle' | 'thinking' | 'error';
export default function IntelligenceCore({ state, compact = false }: { state: CoreState; compact?: boolean }) {
  const reduced = useReducedMotion();
  const thinking = state === 'thinking';
  return <div className={`core-wrap ${compact ? 'core-compact' : ''} core-${state}`} role="img" aria-label={`FRED intelligence core: ${state === 'idle' ? 'ready' : state}`}>
    <div className="core-coordinate coord-top">N 00.00 / F.R.E.D.</div>
    <div className="core-crosshair crosshair-one"/><div className="core-crosshair crosshair-two"/>
    <div className="core-orbit orbit-outer"/>
    <motion.div className="core-orbit orbit-dashed" animate={reduced ? {} : { rotate: 360 }} transition={{ duration: thinking ? 12 : 100, ease: 'linear', repeat: Infinity }}/>
    <motion.div className="core-orbit orbit-ticks" animate={reduced ? {} : { rotate: -360 }} transition={{ duration: thinking ? 20 : 180, ease: 'linear', repeat: Infinity }}/>
    <motion.div className="core-orbit orbit-arc" animate={reduced ? {} : { rotate: 360 }} transition={{ duration: thinking ? 3 : 40, ease: 'linear', repeat: Infinity }}/>
    <div className="core-orbit orbit-inner"/>
    <motion.div className="core-sphere" animate={reduced ? {} : { scale: thinking ? [1, 1.06, 1] : [1, 1.015, 1], opacity: thinking ? [0.72, 1, 0.72] : [0.86, 1, 0.86] }} transition={{ duration: thinking ? 1.5 : 5, repeat: Infinity, ease: 'easeInOut' }}>
      <span className="sphere-latitude latitude-one"/><span className="sphere-latitude latitude-two"/><span className="sphere-longitude longitude-one"/><span className="sphere-longitude longitude-two"/>
      <div className="sphere-center"><span>F</span><span className="sphere-label">FRED</span></div>
    </motion.div>
    <div className="core-coordinate coord-bottom">INTELLIGENCE / 0.1</div>
    <span className="orbit-point point-one"/><span className="orbit-point point-two"/>
  </div>;
}
