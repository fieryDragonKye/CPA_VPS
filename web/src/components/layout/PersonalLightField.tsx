import { useId } from 'react';
import glowNear from '@/assets/light/glow-near.webp';
import glowFar from '@/assets/light/glow-far.webp';
import styles from './PersonalLightField.module.scss';

/** Baked, static soft light behind two moving vector edges. No runtime SVG filters. */
export function PersonalLightField() {
  const id = useId().replace(/:/g, '');
  const ribbons = [
    'M 1080 -160 C 1100 120 930 220 700 355 S 310 490 -180 265 M 700 355 C 1040 240 1240 475 1740 380',
    'M -180 690 C 180 510 450 920 1010 610 S 1520 800 1690 1020 M 1010 610 C 1230 480 1440 140 1660 -100',
  ];
  return (
    <div className={styles.field} aria-hidden="true" data-personal-light-field>
      <div className={styles.atmosphere} />
      <img className={styles.glowNear} src={glowNear} alt="" width="1280" height="800" />
      <img className={styles.glowFar} src={glowFar} alt="" width="1280" height="800" />
      {ribbons.map((d, index) => (
        <div key={index} className={index ? styles.ribbonFar : styles.ribbonNear}>
          <svg viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice" focusable="false">
            <defs>
              <linearGradient
                id={`${id}-${index}`}
                x1="0"
                y1="1"
                x2="1"
                y2="0"
                gradientUnits="objectBoundingBox"
              >
                <stop offset="0" stopColor="#1648bb" stopOpacity="0" />
                <stop offset="0.28" stopColor="#276aff" stopOpacity="0.7" />
                <stop offset="0.56" stopColor="#33cfff" />
                <stop offset="0.68" stopColor="#b5f7ff" />
                <stop offset="0.82" stopColor="#1682ed" stopOpacity="0.8" />
                <stop offset="1" stopColor="#155bcb" stopOpacity="0" />
              </linearGradient>
            </defs>
            <g fill="none" stroke={`url(#${id}-${index})`} strokeLinecap="round">
              <path d={d} strokeWidth="3" opacity="0.3" />
              <path d={d} strokeWidth="1" opacity="0.38" />
            </g>
          </svg>
        </div>
      ))}
    </div>
  );
}
