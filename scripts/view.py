"""Watch a 2D world with Pygame.

Controls:
    SPACE   pause / resume
    A       toggle player AFK (aging pauses while AFK)
    F       turn the clock: fast-forward 500 ticks with aging on
    S       reveal / hide the deity's secrets
    + / -   more / fewer ticks per frame
    ESC     quit

Colors: red/green/blue = food types 0/1/2, brown haze = stink,
white squares = shrines, dots = NPCs (bright = healthy, grey = elder).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pygame  # noqa: E402

from sim import Config, Simulation  # noqa: E402
from sim.snapshot import load_snapshot  # noqa: E402

CELL = 18


def draw(screen, font, sim, show_secrets, paused, speed):
    cfg, w = sim.cfg, sim.world
    rgb = np.zeros((cfg.size, cfg.size, 3))
    for t in range(min(3, cfg.n_food_types)):
        rgb[..., t] = w.food[t] / cfg.food_capacity
    stink = np.clip(w.stink / (2 * cfg.stink_threshold), 0, 1)[..., None]
    rgb = rgb * (1 - 0.6 * stink) + np.array([0.45, 0.3, 0.1]) * 0.6 * stink
    img = (np.clip(rgb, 0, 1) * 200).astype(np.uint8)
    surf = pygame.surfarray.make_surface(img)
    screen.blit(pygame.transform.scale(surf, (cfg.size * CELL, cfg.size * CELL)), (0, 0))

    for s in w.shrines:
        pygame.draw.rect(screen, (255, 255, 255), (s[0] * CELL + 3, s[1] * CELL + 3, CELL - 6, CELL - 6), 2)
    if show_secrets:
        for s in sim.deity.secrets.values():
            c = (s.pos[0] * CELL + CELL // 2, s.pos[1] * CELL + CELL // 2)
            pygame.draw.circle(screen, (255, 215, 0), c, CELL // 3, 1)
    for n in sim.npcs:
        c = (n.pos[0] * CELL + CELL // 2, n.pos[1] * CELL + CELL // 2)
        if n.age >= cfg.old_age:
            color = (150, 150, 150)
        else:
            h = max(0.0, min(1.0, n.health))
            color = (int(255 * (1 - h)), int(255 * h), 255)
        pygame.draw.circle(screen, color, c, CELL // 3)

    status = "PAUSED" if paused else f"x{speed}"
    afk = "AFK (aging paused)" if not sim.clock.player_active else "active"
    text = f"tick {sim.tick}  pop {len(sim.npcs)}  {status}  player {afk}"
    if sim.stats.history:
        h = sim.stats.history[-1]
        text += f"  gen {h['max_generation']}  births {h['births']}  gives {h['gives']}"
    screen.blit(font.render(text, True, (230, 230, 230)), (6, cfg.size * CELL + 6))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", type=str, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--frames", type=int, default=0, help="quit after N frames (0 = run forever)")
    args = ap.parse_args()

    sim = load_snapshot(args.load) if args.load else Simulation(Config(seed=args.seed))
    if sim.cfg.dims != 2:
        sys.exit("The viewer only draws 2D worlds. Use run_headless.py for other dimensions.")

    pygame.init()
    screen = pygame.display.set_mode((sim.cfg.size * CELL, sim.cfg.size * CELL + 30))
    pygame.display.set_caption("Tesseract Folk")
    font = pygame.font.Font(None, 20)
    clock = pygame.time.Clock()
    paused, show_secrets, speed, frames = False, False, 1, 0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_a:
                    sim.clock.player_active = not sim.clock.player_active
                elif event.key == pygame.K_f:
                    sim.fast_forward(500)
                elif event.key == pygame.K_s:
                    show_secrets = not show_secrets
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    speed = min(64, speed * 2)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    speed = max(1, speed // 2)
        if not paused:
            for _ in range(speed):
                sim.step()
        screen.fill((10, 10, 14))
        draw(screen, font, sim, show_secrets, paused, speed)
        pygame.display.flip()
        clock.tick(30)
        frames += 1
        if args.frames and frames >= args.frames:
            running = False
    pygame.quit()


if __name__ == "__main__":
    main()
