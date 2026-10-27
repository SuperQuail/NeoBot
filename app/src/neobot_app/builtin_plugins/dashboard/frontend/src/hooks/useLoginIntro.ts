import { useLayoutEffect, type RefObject } from 'react';
import { gsap } from 'gsap';
import { useReducedEffects } from './useReducedEffects';

/** 一次编排整页开场；清理时归还所有样式，绝不重挂表单或占用输入焦点。 */
export function useLoginIntro(scene: RefObject<HTMLElement>) {
  const reduced = useReducedEffects();

  useLayoutEffect(() => {
    if (reduced || !scene.current) return;
    const context = gsap.context(() => {
      const timeline = gsap.timeline({ defaults: { ease: 'expo.out' } });
      timeline
        .from(
          '.login-brand-panel',
          {
            clipPath: 'inset(0 100% 0 0 round 18px)',
            duration: 0.85,
            ease: 'power4.inOut',
          },
          0,
        )
        .from(
          '[data-login-row]',
          {
            xPercent: (index) => (index === 1 ? 125 : -125),
            rotation: (index) => (index === 1 ? 12 : -8),
            duration: 1.25,
            stagger: 0.1,
          },
          0.12,
        )
        .from(
          '[data-login-letter]',
          {
            yPercent: 120,
            rotationX: -85,
            opacity: 0,
            duration: 0.95,
            stagger: 0.018,
          },
          0.2,
        )
        .fromTo(
          '.login-hero-sweep',
          {
            xPercent: -125,
            opacity: 0.9,
          },
          {
            xPercent: 125,
            opacity: 0,
            duration: 1.05,
            ease: 'power4.inOut',
          },
          0.3,
        )
        .from(
          '.login-card',
          {
            y: 16,
            opacity: 0,
            duration: 0.65,
            clearProps: 'transform,opacity',
          },
          0.3,
        );
    }, scene);
    return () => context.revert();
  }, [scene, reduced]);
}
