import math
from pathlib import Path
import random
import sys
from collections import OrderedDict
from collections import deque
from dataclasses import dataclass

import pygame


WIDTH = 1280
HEIGHT = 720
FPS = 60

ARENA_HALF_SIZE = 16.0
PLAYER_RADIUS = 0.68
PLAYER_HEIGHT = 1.9
PLAYER_SPEED = 13.0
PLAYER_REVERSE_SPEED = 8.0
PLAYER_TURN_SPEED = math.radians(150)
GHOST_DELAY_SECONDS = 5
GHOST_DELAY_FRAMES = GHOST_DELAY_SECONDS * FPS

COIN_RADIUS = 0.55
BOMB_RADIUS = 0.78
BOMB_HEIGHT = 0.95
BOMB_LIFETIME = 3.5
BOMB_SPAWN_MIN = 4.0
BOMB_SPAWN_MAX = 8.0

CAMERA_HISTORY = 14
PLAYER_TRAIL_POINTS = 16
GHOST_TRAIL_POINTS = 14
STAR_COUNT = 100
STAR_SURFACE_CACHE = OrderedDict()
MAX_GLOW_CACHE = 192
MAX_CIRCLE_CACHE = 192
MAX_MISC_CACHE = 128
ENABLE_LIGHT_GLOWS = True

SKY_TOP = (7, 10, 24)
SKY_BOTTOM = (20, 32, 60)
FOG_COLOR = (12, 18, 34)
GROUND_BASE = (10, 18, 30)
GRID_MINOR = (42, 74, 114)
GRID_MAJOR = (82, 166, 246)
PLAYER_COLOR = (82, 224, 150)
PLAYER_HEAD = (255, 230, 205)
PLAYER_GLOW = (82, 255, 190)
GHOST_COLOR = (168, 214, 255)
GHOST_GLOW = (162, 108, 255)
COIN_COLOR = (255, 213, 74)
COIN_GLOW = (255, 194, 70)
BOMB_COLOR = (224, 74, 86)
BOMB_GLOW = (255, 92, 92)
SPARK_COLOR = (255, 184, 84)
NEBULA_GLOW = (62, 180, 255)
RIFT_CORE = (255, 120, 94)
RIFT_OUTER = (118, 96, 255)
TEXT_COLOR = (240, 244, 255)
ACCENT_COLOR = (255, 134, 110)
PANEL_BG = (10, 16, 28, 188)
PANEL_EDGE = (88, 148, 230)

BASE_DIR = Path(__file__).resolve().parent
BGM_PATH = BASE_DIR / "BGM" / "interstellar.mp3"
COIN_SOUND_PATH = BASE_DIR / "Coin_sound" / "koiroylers-get-coin-351945.mp3"


@dataclass
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other):
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def scale(self, value):
        return Vec3(self.x * value, self.y * value, self.z * value)

    def with_y(self, value):
        return Vec3(self.x, value, self.z)


@dataclass
class Particle:
    position: Vec3
    velocity: Vec3
    lifetime: float
    max_lifetime: float
    size: float
    color: tuple
    gravity: float = 0.0

    def update(self, dt):
        self.velocity.y -= self.gravity * dt
        self.position.x += self.velocity.x * dt
        self.position.y += self.velocity.y * dt
        self.position.z += self.velocity.z * dt
        self.lifetime -= dt

    @property
    def alive(self):
        return self.lifetime > 0

    @property
    def alpha(self):
        return max(0.0, self.lifetime / max(self.max_lifetime, 0.001))


@dataclass
class Actor:
    position: Vec3
    forward: Vec3
    heading: float


@dataclass
class Coin:
    position: Vec3
    phase: float


@dataclass
class Bomb:
    position: Vec3
    time_left: float

    def update(self, dt):
        self.time_left -= dt

    def expired(self):
        return self.time_left <= 0


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(start, end, t):
    return (
        int(lerp(start[0], end[0], t)),
        int(lerp(start[1], end[1], t)),
        int(lerp(start[2], end[2], t)),
    )


def average_vec3(values, fallback):
    if not values:
        return fallback
    total_x = sum(value.x for value in values)
    total_y = sum(value.y for value in values)
    total_z = sum(value.z for value in values)
    count = len(values)
    return Vec3(total_x / count, total_y / count, total_z / count)


def normalize_flat(vec, fallback):
    length = math.hypot(vec.x, vec.z)
    if length < 0.001:
        return fallback
    return Vec3(vec.x / length, 0.0, vec.z / length)


def blend_color(color, fog_color, amount):
    return (
        int(lerp(color[0], fog_color[0], amount)),
        int(lerp(color[1], fog_color[1], amount)),
        int(lerp(color[2], fog_color[2], amount)),
    )


class GlowRenderer:
    _glow_cache = OrderedDict()
    _circle_cache = OrderedDict()

    @staticmethod
    def _quantize_color(color):
        return tuple(max(0, min(255, int(round(channel / 16) * 16))) for channel in color)

    @staticmethod
    def _quantize_alpha(alpha):
        return max(0, min(255, int(round(alpha / 16) * 16)))

    @staticmethod
    def _touch(cache, key, value, limit):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)

    @classmethod
    def _get_glow(cls, radius, color, alpha):
        radius = max(1, int(radius))
        color = cls._quantize_color(color)
        alpha = cls._quantize_alpha(alpha)
        key = (radius, color, alpha)
        cached = cls._glow_cache.get(key)
        if cached is not None:
            cls._glow_cache.move_to_end(key)
            return cached

        glow = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        for layer in range(3, 0, -1):
            scale = layer / 3
            layer_radius = max(1, int(radius * scale))
            layer_alpha = int(alpha * (0.22 + scale * 0.18))
            pygame.draw.circle(
                glow,
                (*color, layer_alpha),
                (glow.get_width() // 2, glow.get_height() // 2),
                layer_radius,
            )
        cls._touch(cls._glow_cache, key, glow, MAX_GLOW_CACHE)
        return glow

    @classmethod
    def get_circle(cls, radius, color, alpha):
        radius = max(1, int(radius))
        color = cls._quantize_color(color)
        alpha = cls._quantize_alpha(alpha)
        key = (radius, color, alpha)
        cached = cls._circle_cache.get(key)
        if cached is not None:
            cls._circle_cache.move_to_end(key)
            return cached

        circle = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(circle, (*color, alpha), (radius + 2, radius + 2), radius)
        cls._touch(cls._circle_cache, key, circle, MAX_CIRCLE_CACHE)
        return circle

    @staticmethod
    def draw_glow(surface, center, radius, color, alpha):
        if radius <= 1 or alpha <= 0:
            return
        if radius < 4 and alpha < 24:
            return
        glow = GlowRenderer._get_glow(radius, color, alpha)
        surface.blit(glow, glow.get_rect(center=(int(center[0]), int(center[1]))))


class TrailRenderer:
    def draw(self, surface, camera, samples, color, radius, glow_color, alpha_scale=1.0):
        projected = [camera.project(position) for position in samples]
        projected = [proj for proj in projected if proj]
        count = len(projected)
        if not count:
            return

        for index, proj in enumerate(projected):
            age = (index + 1) / count
            alpha = int(110 * age * alpha_scale)
            size = max(2, int(radius * proj[2] * age))
            GlowRenderer.draw_glow(surface, proj[:2], size * 2, glow_color, alpha)
            circle = GlowRenderer.get_circle(size, color, min(255, alpha + 30))
            surface.blit(circle, (proj[0] - size - 2, proj[1] - size - 2))


class ParticleEngine:
    def __init__(self):
        self.particles = []
        self.max_particles = 220

    def emit(self, position, color, count, speed_range, size_range, life_range, gravity=0.0):
        count = min(count, max(0, self.max_particles - len(self.particles)))
        for _ in range(count):
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(speed_range[0], speed_range[1])
            max_life = random.uniform(life_range[0], life_range[1])
            velocity = Vec3(
                math.cos(angle) * speed,
                random.uniform(speed * 0.2, speed * 0.7),
                math.sin(angle) * speed,
            )
            self.particles.append(
                Particle(
                    position=Vec3(position.x, position.y, position.z),
                    velocity=velocity,
                    lifetime=max_life,
                    max_lifetime=max_life,
                    size=random.uniform(size_range[0], size_range[1]),
                    color=color,
                    gravity=gravity,
                )
            )

    def emit_glitch(self, position, color, count):
        count = min(count, max(0, self.max_particles - len(self.particles)))
        for _ in range(count):
            self.particles.append(
                Particle(
                    position=Vec3(
                        position.x + random.uniform(-0.5, 0.5),
                        position.y + random.uniform(0.6, 1.9),
                        position.z + random.uniform(-0.5, 0.5),
                    ),
                    velocity=Vec3(
                        random.uniform(-0.8, 0.8),
                        random.uniform(-0.2, 0.8),
                        random.uniform(-0.8, 0.8),
                    ),
                    lifetime=random.uniform(0.22, 0.45),
                    max_lifetime=0.45,
                    size=random.uniform(0.06, 0.14),
                    color=color,
                )
            )

    def update(self, dt):
        alive = []
        for particle in self.particles:
            particle.update(dt)
            if particle.alive:
                alive.append(particle)
        self.particles = alive

    def draw(self, surface, camera, fog_color):
        items = []
        for particle in self.particles:
            proj = camera.project(particle.position)
            if proj:
                items.append((proj[3], particle, proj))

        items.sort(key=lambda item: item[0], reverse=True)
        for depth, particle, proj in items:
            fade = particle.alpha
            size = max(1, int(particle.size * proj[2]))
            color = blend_color(particle.color, fog_color, clamp((depth - 16.0) / 40.0, 0.0, 0.72))
            alpha = int(255 * fade)
            GlowRenderer.draw_glow(surface, proj[:2], size * 3, color, int(alpha * 0.45))
            sprite = GlowRenderer.get_circle(size, color, alpha)
            surface.blit(sprite, (proj[0] - size - 2, proj[1] - size - 2))


class Camera:
    def __init__(self):
        self.position = Vec3(0.0, 6.0, -8.5)
        self.pitch = math.radians(18)
        self.yaw = 0.0
        self.roll = 0.0
        self.shake_time = 0.0
        self.shake_strength = 0.0
        self.shake_offset = (0.0, 0.0)
        self.fov = math.radians(84)
        self.focal_length = (WIDTH / 2) / math.tan(self.fov / 2)
        self.position_samples = deque(maxlen=CAMERA_HISTORY)
        self.forward_samples = deque(maxlen=CAMERA_HISTORY)

    def add_shake(self, strength, duration):
        self.shake_strength = max(self.shake_strength, strength)
        self.shake_time = max(self.shake_time, duration)

    def update_follow(self, target, forward, turn_input, dt):
        forward = normalize_flat(forward, Vec3(0.0, 0.0, 1.0))
        self.forward_samples.append(forward)
        smooth_forward = normalize_flat(average_vec3(self.forward_samples, forward), forward)
        self.yaw = math.atan2(smooth_forward.x, smooth_forward.z)

        distance_back = 7.6
        height = 4.2
        target_position = Vec3(
            target.x - smooth_forward.x * distance_back,
            height,
            target.z - smooth_forward.z * distance_back,
        )
        self.position_samples.append(target_position)
        self.position = average_vec3(self.position_samples, target_position)

        target_roll = -turn_input * math.radians(2.3)
        self.roll = lerp(self.roll, target_roll, min(1.0, dt * 8.5))

        if self.shake_time > 0.0:
            previous_time = self.shake_time
            self.shake_time -= dt
            intensity = self.shake_strength * (max(self.shake_time, 0.0) / max(previous_time, 0.001))
            self.shake_offset = (
                random.uniform(-1.0, 1.0) * intensity,
                random.uniform(-1.0, 1.0) * intensity,
            )
            self.shake_strength = lerp(self.shake_strength, 0.0, min(1.0, dt * 8.0))
        else:
            self.shake_strength = 0.0
            self.shake_offset = (0.0, 0.0)

    def world_to_camera(self, point):
        relative = point - self.position
        cos_yaw = math.cos(self.yaw)
        sin_yaw = math.sin(self.yaw)
        yaw_x = relative.x * cos_yaw - relative.z * sin_yaw
        yaw_z = relative.x * sin_yaw + relative.z * cos_yaw

        cos_pitch = math.cos(self.pitch)
        sin_pitch = math.sin(self.pitch)
        cam_y = relative.y * cos_pitch + yaw_z * sin_pitch
        cam_z = yaw_z * cos_pitch - relative.y * sin_pitch
        return Vec3(yaw_x, cam_y, cam_z)

    def project(self, point):
        cam_point = self.world_to_camera(point)
        if cam_point.z <= 0.15:
            return None

        scale = self.focal_length / cam_point.z
        screen_x = WIDTH / 2 + cam_point.x * scale
        screen_y = HEIGHT / 2 - cam_point.y * scale

        if abs(self.roll) > 0.0001:
            rel_x = screen_x - WIDTH / 2
            rel_y = screen_y - HEIGHT / 2
            cos_roll = math.cos(self.roll)
            sin_roll = math.sin(self.roll)
            rot_x = rel_x * cos_roll - rel_y * sin_roll
            rot_y = rel_x * sin_roll + rel_y * cos_roll
            screen_x = WIDTH / 2 + rot_x
            screen_y = HEIGHT / 2 + rot_y

        screen_x += self.shake_offset[0]
        screen_y += self.shake_offset[1]
        return screen_x, screen_y, scale, cam_point.z


class Renderer3D:
    def __init__(self, screen):
        self.screen = screen
        self.camera = Camera()
        self.trail_renderer = TrailRenderer()
        self.star_field = self._build_star_field()
        self.skyline_towers = self._build_skyline_towers()
        self.energy_shards = self._build_energy_shards()
        self.sky_surface = self._build_sky_surface()

    def _build_sky_surface(self):
        sky = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            t = y / max(HEIGHT - 1, 1)
            pygame.draw.line(sky, lerp_color(SKY_TOP, SKY_BOTTOM, t), (0, y), (WIDTH, y))
        return sky

    def _get_misc_surface(self, key, builder):
        cached = STAR_SURFACE_CACHE.get(key)
        if cached is not None:
            STAR_SURFACE_CACHE.move_to_end(key)
            return cached
        surface = builder()
        STAR_SURFACE_CACHE[key] = surface
        while len(STAR_SURFACE_CACHE) > MAX_MISC_CACHE:
            STAR_SURFACE_CACHE.popitem(last=False)
        return surface

    def _build_star_field(self):
        rng = random.Random(42)
        stars = []
        for _ in range(STAR_COUNT):
            stars.append(
                (
                    rng.randint(0, WIDTH - 1),
                    rng.randint(12, int(HEIGHT * 0.58)),
                    rng.randint(1, 3),
                    rng.randint(130, 255),
                    rng.uniform(0.4, 1.3),
                )
            )
        return stars

    def _build_skyline_towers(self):
        rng = random.Random(7)
        towers = []
        for lane_x in (-27, -23, -19, 19, 23, 27):
            for z in range(-8, 68, 8):
                towers.append(
                    (
                        Vec3(lane_x + rng.uniform(-1.0, 1.0), 0.0, z + rng.uniform(-1.0, 1.2)),
                        rng.uniform(1.8, 3.2),
                        rng.uniform(5.0, 12.0),
                        rng.randint(0, 999),
                    )
                )
        return towers

    def _build_energy_shards(self):
        rng = random.Random(19)
        shards = []
        for _ in range(34):
            side = -1 if rng.random() < 0.5 else 1
            shards.append(
                (
                    Vec3(
                        side * rng.uniform(13.0, 24.0),
                        rng.uniform(2.6, 8.8),
                        rng.uniform(-10.0, 60.0),
                    ),
                    rng.uniform(0.0, math.tau),
                )
            )
        return shards

    def fog_amount(self, depth):
        return clamp((depth - 18.0) / 38.0, 0.0, 0.78)

    def fog_colorize(self, color, depth):
        return blend_color(color, FOG_COLOR, self.fog_amount(depth))

    def draw_background(self, world_time):
        self.screen.blit(self.sky_surface, (0, 0))
        self.draw_time_rift(world_time)
        self.draw_stars(world_time)

    def draw_stars(self, world_time):
        for x, y, radius, alpha, drift in self.star_field:
            parallax_x = (x - self.camera.yaw * 180 - world_time * drift * 3) % WIDTH
            parallax_y = y + math.sin(world_time * drift + x * 0.01) * 6
            twinkle = 0.72 + 0.28 * math.sin(world_time * drift * 4 + x * 0.05)
            twinkle_alpha = int(alpha * twinkle)
            star_key = (radius, twinkle_alpha)
            star = self._get_misc_surface(
                ("star",) + star_key,
                lambda: self._build_star_sprite(radius, twinkle_alpha),
            )
            self.screen.blit(star, (parallax_x - radius * 2, parallax_y - radius * 2))

    def _build_star_sprite(self, radius, alpha):
        star = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(star, (255, 255, 255, alpha), (radius * 2, radius * 2), radius)
        return star

    def draw_time_rift(self, world_time):
        center = (WIDTH // 2, int(HEIGHT * 0.2 + math.sin(world_time * 0.8) * 8))
        pulse = 1.0 + math.sin(world_time * 1.9) * 0.08
        layers = [
            (340 * pulse, 120 * pulse, (*RIFT_OUTER, 28)),
            (260 * pulse, 92 * pulse, (*NEBULA_GLOW, 34)),
            (188 * pulse, 66 * pulse, (*RIFT_CORE, 48)),
        ]
        for width, height, color in layers:
            surface = pygame.Surface((int(width * 2), int(height * 2)), pygame.SRCALPHA)
            pygame.draw.ellipse(surface, color, surface.get_rect())
            self.screen.blit(surface, (center[0] - width, center[1] - height))

        for index in range(7):
            orbit_w = int((170 + index * 32) * pulse)
            orbit_h = int((30 + index * 9) * pulse)
            sway = math.sin(world_time * 1.6 + index) * 0.08
            color = lerp_color(RIFT_CORE, RIFT_OUTER, index / 6)
            pygame.draw.arc(
                self.screen,
                color,
                (center[0] - orbit_w, center[1] - orbit_h, orbit_w * 2, orbit_h * 2),
                math.pi * (0.12 + sway),
                math.pi * (0.88 + sway),
                2,
            )

    def draw_world_environment(self, world_time):
        self.draw_horizon_portal(world_time)
        self.draw_neon_rails(world_time)
        self.draw_skyline_towers(world_time)
        self.draw_energy_shards(world_time)

    def draw_horizon_portal(self, world_time):
        center = Vec3(0.0, 8.2 + math.sin(world_time * 1.6) * 0.3, 56.0)
        proj = self.camera.project(center)
        if not proj:
            return
        screen_x, screen_y, scale, depth = proj
        ring_specs = [
            (12.5, 3.0, RIFT_OUTER, 3),
            (9.2, 2.25, NEBULA_GLOW, 2),
            (6.4, 1.55, RIFT_CORE, 2),
        ]
        for idx, (width_world, height_world, color, line_width) in enumerate(ring_specs):
            wobble = 1.0 + math.sin(world_time * 2.0 + idx) * 0.05
            width = max(44, int(width_world * scale * wobble))
            height = max(12, int(height_world * scale * wobble))
            rect = pygame.Rect(int(screen_x - width), int(screen_y - height), width * 2, height * 2)
            draw_color = self.fog_colorize(color, depth)
            pygame.draw.arc(self.screen, draw_color, rect, math.pi * 0.05, math.pi * 0.95, line_width)
            pygame.draw.arc(
                self.screen,
                draw_color,
                rect.inflate(-width // 3, -height // 3),
                math.pi * 1.05,
                math.pi * 1.95,
                line_width,
            )
            if width < 180:
                GlowRenderer.draw_glow(self.screen, (screen_x, screen_y), width, draw_color, 28)

    def draw_neon_rails(self, world_time):
        rail_offsets = (-12.5, -9.5, 9.5, 12.5)
        if not hasattr(self, '_cached_neon_rails'):
            self._cached_neon_rails = []
            for rail_x in rail_offsets:
                self._cached_neon_rails.append([Vec3(rail_x, 0.05, float(z)) for z in range(-8, 70, 3)])
                
            self._cached_neon_beacons = []
            for rail_x in rail_offsets:
                self._cached_neon_beacons.extend([Vec3(rail_x, 0.0, float(z)) for z in range(-8, 70, 8)])

        for idx, rail_x in enumerate(rail_offsets):
            prev = None
            for point_vec in self._cached_neon_rails[idx]:
                point = self.camera.project(point_vec)
                if point and prev:
                    color = (72, 164, 255) if abs(rail_x) < 11 else (120, 96, 255)
                    color = self.fog_colorize(color, point[3])
                    pygame.draw.line(
                        self.screen,
                        color,
                        (int(prev[0]), int(prev[1])),
                        (int(point[0]), int(point[1])),
                        2,
                    )
                    if point[3] < 26:
                        GlowRenderer.draw_glow(self.screen, point[:2], 6, color, 14)
                prev = point

        for beacon_pos in self._cached_neon_beacons:
            self.draw_beacon(beacon_pos, world_time)

    def draw_beacon(self, position, world_time):
        bottom = self.camera.project(position)
        top = self.camera.project(position + Vec3(0.0, 2.6, 0.0))
        if not bottom or not top:
            return
        width = max(3, int(0.18 * bottom[2]))
        depth = bottom[3]
        color = self.fog_colorize((68, 96, 158), depth)
        rect = pygame.Rect(int(bottom[0] - width / 2), int(top[1]), width, max(4, int(bottom[1] - top[1])))
        pygame.draw.rect(self.screen, color, rect, border_radius=2)
        glow_strength = 0.6 + 0.4 * math.sin(world_time * 4 + position.z * 0.25)
        light_color = self.fog_colorize((116, 224, 255), depth)
        light_y = int(top[1] - width * 0.6)
        pygame.draw.circle(self.screen, light_color, (int(top[0]), light_y), max(2, width // 2))
        if depth < 28:
            GlowRenderer.draw_glow(self.screen, (top[0], light_y), width * 3, light_color, int(42 * glow_strength))

    def draw_skyline_towers(self, world_time):
        visible = []
        for pos, width, height, seed in self.skyline_towers:
            point = self.camera.project(pos)
            if point:
                visible.append((point[3], pos, width, height, seed))

        visible.sort(key=lambda item: item[0], reverse=True)
        for depth, pos, width, height, seed in visible:
            self.draw_tower(pos, width, height, seed, depth, world_time)

    def draw_tower(self, base, width, height, seed, depth, world_time):
        bottom = self.camera.project(base)
        top = self.camera.project(base + Vec3(0.0, height, 0.0))
        if not bottom or not top:
            return
        tower_width = max(8, int(width * bottom[2]))
        rect = pygame.Rect(
            int(bottom[0] - tower_width / 2),
            int(top[1]),
            tower_width,
            max(12, int(bottom[1] - top[1])),
        )
        body_color = self.fog_colorize((12, 20, 40), depth)
        edge_color = self.fog_colorize((82, 132, 210), depth)
        pygame.draw.rect(self.screen, body_color, rect)
        pygame.draw.rect(self.screen, edge_color, rect, 1)

        pulse = int(world_time * 4 + seed) % 8
        for row in range(rect.y + 8, rect.bottom - 10, 16):
            inset = 4
            usable_width = max(0, rect.width - inset * 2)
            window_count = max(1, usable_width // 12)
            for idx in range(window_count):
                wx = rect.x + inset + idx * 12
                if wx + 4 < rect.right - inset and (idx + row // 8 + pulse) % 3 == 0:
                    pygame.draw.rect(
                        self.screen,
                        self.fog_colorize((126, 212, 255), depth),
                        (wx, row, 4, 7),
                    )

    def draw_energy_shards(self, world_time):
        visible = []
        for center, phase in self.energy_shards:
            drift = Vec3(center.x, center.y + math.sin(world_time * 1.6 + phase) * 0.22, center.z)
            proj = self.camera.project(drift)
            if proj:
                visible.append((proj[3], drift, phase))
        visible.sort(reverse=True)
        for depth, center, phase in visible:
            self.draw_shard(center, depth, phase, world_time)

    def draw_shard(self, center, depth, phase, world_time):
        proj = self.camera.project(center)
        if not proj:
            return
        screen_x, screen_y, scale, _ = proj
        size = max(4, int(scale * 0.25))
        pulse = 1.0 + math.sin(world_time * 3.0 + phase) * 0.2
        size = int(size * pulse)
        points = [
            (screen_x, screen_y - size),
            (screen_x + size * 0.7, screen_y),
            (screen_x, screen_y + size),
            (screen_x - size * 0.7, screen_y),
        ]
        base_color = (140, 224, 255) if center.x < 0 else (184, 120, 255)
        color = self.fog_colorize(base_color, depth)
        if depth < 26:
            GlowRenderer.draw_glow(self.screen, (screen_x, screen_y), size * 2, color, 24)
        pygame.draw.polygon(self.screen, color, points)
        pygame.draw.polygon(self.screen, (255, 255, 255), points, 1)

    def draw_ground(self, world_time):
        center = Vec3(0.0, 0.0, 0.0)
        proj = self.camera.project(center)
        if proj:
            ground_y = int(proj[1])
            if ground_y < HEIGHT:
                pygame.draw.rect(self.screen, GROUND_BASE, (0, ground_y, WIDTH, HEIGHT - ground_y))

        if not hasattr(self, '_cached_grid_lines_z'):
            self._cached_grid_lines_z = []
            for coord in range(-20, 21):
                self._cached_grid_lines_z.append([Vec3(coord, 0.02, float(z)) for z in range(-8, 72, 3)])
                
            self._cached_grid_lines_x = []
            for coord in range(-8, 73, 3):
                self._cached_grid_lines_x.append((Vec3(-ARENA_HALF_SIZE, 0.02, coord), Vec3(ARENA_HALF_SIZE, 0.02, coord)))

        for line_idx, coord in enumerate(range(-20, 21)):
            major = coord % 4 == 0
            base_color = GRID_MAJOR if major else GRID_MINOR
            prev = None
            for point_vec in self._cached_grid_lines_z[line_idx]:
                point = self.camera.project(point_vec)
                if point and prev:
                    color = self.fog_colorize(base_color, point[3])
                    width = 2 if major else 1
                    pygame.draw.line(
                        self.screen,
                        color,
                        (int(prev[0]), int(prev[1])),
                        (int(point[0]), int(point[1])),
                        width,
                    )
                    if major and point[3] < 24:
                        GlowRenderer.draw_glow(self.screen, point[:2], 4, base_color, 10)
                prev = point

        for line_idx, coord in enumerate(range(-8, 73, 3)):
            major = coord % 12 == 0
            base_color = GRID_MAJOR if major else GRID_MINOR
            start_vec, end_vec = self._cached_grid_lines_x[line_idx]
            start = self.camera.project(start_vec)
            end = self.camera.project(end_vec)
            if start and end:
                color = self.fog_colorize(base_color, end[3])
                pygame.draw.line(
                    self.screen,
                    color,
                    (int(start[0]), int(start[1])),
                    (int(end[0]), int(end[1])),
                    2 if major else 1,
                )

        for layer in range(4):
            band_y = int(HEIGHT * (0.58 + layer * 0.11))
            band = pygame.Surface((WIDTH, 32), pygame.SRCALPHA)
            pygame.draw.rect(band, (*FOG_COLOR, 24 + layer * 12), band.get_rect())
            self.screen.blit(band, (0, band_y))

    def draw_shadow(self, position, radius, alpha=60):
        proj = self.camera.project(position.with_y(0.02))
        if not proj:
            return
        screen_x, screen_y, scale, _ = proj
        shadow_w = max(4, int(radius * scale * 1.45))
        shadow_h = max(2, int(radius * scale * 0.5))
        shadow_key = ("shadow", shadow_w, shadow_h, int(round(alpha / 16) * 16))
        surface = self._get_misc_surface(
            shadow_key,
            lambda: self._build_shadow_sprite(shadow_w, shadow_h, shadow_key[3]),
        )
        self.screen.blit(surface, (screen_x - shadow_w - 2, screen_y - shadow_h - 1))

    def _build_shadow_sprite(self, shadow_w, shadow_h, alpha):
        surface = pygame.Surface((shadow_w * 2 + 4, shadow_h * 2 + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(surface, (0, 0, 0, alpha), (2, 2, shadow_w * 2, shadow_h * 2))
        return surface

    def draw_cylinder(self, position, radius, height, body_color, top_color, depth, alpha=255):
        bottom = self.camera.project(position)
        top = self.camera.project(position + Vec3(0.0, height, 0.0))
        if not bottom or not top:
            return
        body_color = self.fog_colorize(body_color, depth)
        top_color = self.fog_colorize(top_color, depth)

        base_radius = max(4, int(radius * bottom[2]))
        top_radius = max(3, int(radius * top[2]))
        body_width = max(base_radius * 2, top_radius * 2)
        body_rect = pygame.Rect(
            int(bottom[0] - body_width / 2),
            int(top[1]),
            int(body_width),
            max(4, int(bottom[1] - top[1])),
        )

        body = pygame.Surface((body_rect.width, body_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(body, (*body_color, alpha), body.get_rect(), border_radius=max(2, body_width // 4))
        self.screen.blit(body, body_rect.topleft)
        pygame.draw.ellipse(
            self.screen,
            (*top_color, alpha),
            (int(top[0] - top_radius), int(top[1] - top_radius * 0.6), top_radius * 2, max(4, int(top_radius * 1.2))),
        )

    def draw_player(self, player, world_time, trail_points, ghost=False):
        depth_proj = self.camera.project(player.position)
        if not depth_proj:
            return
        depth = depth_proj[3]

        body_color = GHOST_COLOR if ghost else PLAYER_COLOR
        head_color = GHOST_COLOR if ghost else PLAYER_HEAD
        glow_color = GHOST_GLOW if ghost else PLAYER_GLOW
        bob = math.sin(world_time * 8.0 + player.heading * 2.0) * 0.08
        body_position = player.position + Vec3(0.0, bob, 0.0)
        alpha = int(150 + 55 * math.sin(world_time * 18.0)) if ghost else 255

        self.trail_renderer.draw(
            self.screen,
            self.camera,
            trail_points,
            GHOST_COLOR if ghost else PLAYER_COLOR,
            PLAYER_RADIUS * 0.42,
            glow_color,
            alpha_scale=0.55 if ghost else 0.4,
        )
        if depth < 22:
            GlowRenderer.draw_glow(self.screen, depth_proj[:2], int(14 * depth_proj[2] / 10), glow_color, 42 if ghost else 54)
        self.draw_shadow(body_position, PLAYER_RADIUS, alpha=45 if ghost else 62)
        self.draw_cylinder(body_position, PLAYER_RADIUS, PLAYER_HEIGHT * 0.62, body_color, body_color, depth, alpha=alpha)

        torso_top = body_position + Vec3(0.0, PLAYER_HEIGHT * 0.62, 0.0)
        head_center = torso_top + Vec3(0.0, PLAYER_HEIGHT * 0.25, 0.0)
        head_proj = self.camera.project(head_center)
        if head_proj:
            head_radius = max(5, int(0.33 * head_proj[2]))
            if head_proj[3] < 20:
                GlowRenderer.draw_glow(self.screen, head_proj[:2], head_radius * 2, glow_color, 26 if ghost else 32)
            head_surface = GlowRenderer.get_circle(head_radius, self.fog_colorize(head_color, head_proj[3]), alpha)
            self.screen.blit(head_surface, (head_proj[0] - head_radius - 2, head_proj[1] - head_radius - 2))

    def draw_coin(self, coin, world_time):
        hover = math.sin(world_time * 3.4 + coin.phase) * 0.32
        position = coin.position + Vec3(0.0, 1.15 + hover, 0.0)
        proj = self.camera.project(position)
        if not proj:
            return
        depth = proj[3]
        radius = max(4, int(COIN_RADIUS * proj[2]))
        width = max(4, int(radius * (0.24 + abs(math.sin(world_time * 4.2 + coin.phase)) * 0.9)))
        rect = pygame.Rect(int(proj[0] - width), int(proj[1] - radius), width * 2, radius * 2)
        color = self.fog_colorize(COIN_COLOR, depth)
        if depth < 28:
            GlowRenderer.draw_glow(self.screen, proj[:2], radius * 3, COIN_GLOW, 46)
        pygame.draw.ellipse(self.screen, color, rect)
        pygame.draw.ellipse(self.screen, self.fog_colorize((255, 241, 168), depth), rect.inflate(-max(2, width // 2), -max(2, radius // 2)))
        pygame.draw.ellipse(self.screen, self.fog_colorize((164, 120, 20), depth), rect, 2)

    def draw_bomb(self, bomb, world_time):
        proj = self.camera.project(bomb.position)
        if not proj:
            return
        depth = proj[3]
        pulse = 0.55 + 0.45 * math.sin((BOMB_LIFETIME - bomb.time_left) * 9.0)
        if depth < 30:
            GlowRenderer.draw_glow(self.screen, proj[:2], int(14 * pulse), BOMB_GLOW, 38)
        self.draw_shadow(bomb.position, BOMB_RADIUS, alpha=52)
        self.draw_cylinder(bomb.position, BOMB_RADIUS, BOMB_HEIGHT, BOMB_COLOR, BOMB_COLOR, depth)
        spark = bomb.position + Vec3(0.35, BOMB_HEIGHT + 0.42, -0.15)
        spark_proj = self.camera.project(spark)
        if spark_proj:
            radius = max(3, int(0.2 * spark_proj[2]))
            color = self.fog_colorize(SPARK_COLOR, spark_proj[3])
            pygame.draw.circle(self.screen, color, (int(spark_proj[0]), int(spark_proj[1])), radius)
            if spark_proj[3] < 18:
                GlowRenderer.draw_glow(self.screen, spark_proj[:2], radius * 3, SPARK_COLOR, 28)

    def draw_arena_bounds(self):
        corners = [
            Vec3(-ARENA_HALF_SIZE, 0.0, -ARENA_HALF_SIZE),
            Vec3(ARENA_HALF_SIZE, 0.0, -ARENA_HALF_SIZE),
            Vec3(ARENA_HALF_SIZE, 0.0, ARENA_HALF_SIZE),
            Vec3(-ARENA_HALF_SIZE, 0.0, ARENA_HALF_SIZE),
        ]
        projected = [self.camera.project(corner) for corner in corners]
        if any(point is None for point in projected):
            return
        pygame.draw.lines(
            self.screen,
            (114, 158, 224),
            True,
            [(int(point[0]), int(point[1])) for point in projected],
            3,
        )


class Game:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption("Time Travel Runner 3D")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.renderer = Renderer3D(self.screen)
        self.particles = ParticleEngine()
        self.audio_enabled = False
        self.coin_sound = None
        self._setup_audio()

        self.title_font = pygame.font.SysFont("arial", 58, bold=True)
        self.ui_font = pygame.font.SysFont("arial", 28, bold=True)
        self.small_font = pygame.font.SysFont("arial", 21)

        self.running = True
        self.state = "start"
        self.total_time = 0.0
        self.start_overlay_alpha = 255.0
        self.last_turn_input = 0.0
        self.reset()

    def _setup_audio(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.audio_enabled = True
        except pygame.error:
            self.audio_enabled = False
            return

        try:
            if BGM_PATH.exists():
                pygame.mixer.music.load(str(BGM_PATH))
                pygame.mixer.music.set_volume(0.45)
                pygame.mixer.music.play(-1)
        except pygame.error:
            self.audio_enabled = False

        try:
            if self.audio_enabled and COIN_SOUND_PATH.exists():
                self.coin_sound = pygame.mixer.Sound(str(COIN_SOUND_PATH))
                self.coin_sound.set_volume(0.65)
        except pygame.error:
            self.coin_sound = None

    def reset(self):
        self.player = Actor(Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 1.0), 0.0)
        self.ghost = Actor(Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 1.0), 0.0)
        self.ghost_active = False
        self.position_history = deque(maxlen=GHOST_DELAY_FRAMES + 1)
        self.player_trail = deque(maxlen=PLAYER_TRAIL_POINTS)
        self.ghost_trail = deque(maxlen=GHOST_TRAIL_POINTS)
        self.survival_time = 0.0
        self.score = 0
        self.bombs = []
        self.coin = self.spawn_coin()
        self.bomb_timer = random.uniform(BOMB_SPAWN_MIN, BOMB_SPAWN_MAX)
        self.particles.particles.clear()
        self.start_overlay_alpha = 255.0
        self.renderer.camera.position_samples.clear()
        self.renderer.camera.forward_samples.clear()
        self.renderer.camera.update_follow(self.player.position, self.player.forward, 0.0, 0.016)

    def start_game(self):
        self.reset()
        self.state = "playing"

    def end_game(self):
        self.state = "game_over"
        self.renderer.camera.add_shake(10.0, 0.45)
        self.particles.emit(self.player.position + Vec3(0.0, 0.9, 0.0), BOMB_GLOW, 16, (1.2, 3.4), (0.08, 0.16), (0.28, 0.62), gravity=2.2)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if self.state == "start" and event.key == pygame.K_SPACE:
                    self.start_game()
                elif self.state == "game_over" and event.key == pygame.K_r:
                    self.start_game()
                elif event.key == pygame.K_ESCAPE:
                    self.running = False

    def random_position(self, radius, avoid_center=False):
        for _ in range(100):
            x = random.uniform(-ARENA_HALF_SIZE + radius, ARENA_HALF_SIZE - radius)
            z = random.uniform(-ARENA_HALF_SIZE + radius, ARENA_HALF_SIZE - radius)
            position = Vec3(x, 0.0, z)
            if avoid_center and (position.x**2 + position.z**2) < 9.0:
                continue
            return position
        return Vec3(5.0, 0.0, 5.0)

    def distance_sq_2d(self, a, b):
        return (a.x - b.x)**2 + (a.z - b.z)**2

    def spawn_coin(self):
        for _ in range(100):
            position = self.random_position(COIN_RADIUS, avoid_center=True)
            if self.distance_sq_2d(position, self.player.position) < 6.25:
                continue
            if self.ghost_active and self.distance_sq_2d(position, self.ghost.position) < 6.25:
                continue
            if any(self.distance_sq_2d(position, bomb.position) < 4.0 for bomb in self.bombs):
                continue
            return Coin(position, random.uniform(0.0, math.tau))
        return Coin(Vec3(6.0, 0.0, 6.0), 0.0)

    def spawn_bomb(self):
        for _ in range(100):
            position = self.random_position(BOMB_RADIUS, avoid_center=True)
            if self.distance_sq_2d(position, self.player.position) < 9.0:
                continue
            if self.ghost_active and self.distance_sq_2d(position, self.ghost.position) < 9.0:
                continue
            if self.coin and self.distance_sq_2d(position, self.coin.position) < 4.0:
                continue
            if any(self.distance_sq_2d(position, bomb.position) < 4.0 for bomb in self.bombs):
                continue
            self.bombs.append(Bomb(position, BOMB_LIFETIME))
            return

    def explode_bomb(self, bomb):
        self.particles.emit(bomb.position + Vec3(0.0, 0.5, 0.0), BOMB_GLOW, 18, (1.4, 4.2), (0.1, 0.2), (0.3, 0.7), gravity=2.8)
        self.renderer.camera.add_shake(8.0, 0.28)

    def update_bombs(self, dt):
        self.bomb_timer -= dt
        if self.bomb_timer <= 0:
            self.spawn_bomb()
            self.bomb_timer = random.uniform(BOMB_SPAWN_MIN, BOMB_SPAWN_MAX)

        alive_bombs = []
        for bomb in self.bombs:
            bomb.update(dt)
            if bomb.expired():
                self.explode_bomb(bomb)
            else:
                alive_bombs.append(bomb)
        self.bombs = alive_bombs

    def update_player(self, dt):
        keys = pygame.key.get_pressed()
        turn_input = 0.0
        move_input = 0.0

        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            turn_input -= 1.0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            turn_input += 1.0
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            move_input += 1.0
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            move_input -= 1.0

        self.last_turn_input = turn_input
        self.player.heading += turn_input * PLAYER_TURN_SPEED * dt
        self.player.forward = Vec3(math.sin(self.player.heading), 0.0, math.cos(self.player.heading))

        move_speed = PLAYER_SPEED if move_input >= 0 else PLAYER_REVERSE_SPEED
        self.player.position.x += self.player.forward.x * move_input * move_speed * dt
        self.player.position.z += self.player.forward.z * move_input * move_speed * dt
        self.player.position.x = clamp(self.player.position.x, -ARENA_HALF_SIZE + PLAYER_RADIUS, ARENA_HALF_SIZE - PLAYER_RADIUS)
        self.player.position.z = clamp(self.player.position.z, -ARENA_HALF_SIZE + PLAYER_RADIUS, ARENA_HALF_SIZE - PLAYER_RADIUS)
        self.player_trail.appendleft(self.player.position + Vec3(0.0, 0.22, 0.0))
        self.renderer.camera.update_follow(self.player.position, self.player.forward, turn_input, dt)

    def update_ghost(self):
        self.position_history.append(
            (
                Vec3(self.player.position.x, 0.0, self.player.position.z),
                self.player.forward,
                self.player.heading,
            )
        )
        delayed_position = None
        if len(self.position_history) > GHOST_DELAY_FRAMES:
            delayed_position = self.position_history[0]

        if delayed_position is None:
            self.ghost_active = False
            return

        self.ghost_active = True
        self.ghost.position = delayed_position[0]
        self.ghost.forward = delayed_position[1]
        self.ghost.heading = delayed_position[2]
        self.ghost_trail.appendleft(self.ghost.position + Vec3(0.0, 0.4, 0.0))

        if random.random() < 0.2:
            self.particles.emit_glitch(self.ghost.position + Vec3(0.0, 0.9, 0.0), GHOST_GLOW, 2)

    def update(self, dt):
        self.total_time += dt
        self.start_overlay_alpha = max(0.0, self.start_overlay_alpha - dt * 180)
        self.update_player(dt)
        self.update_ghost()
        self.survival_time += dt
        self.update_bombs(dt)
        self.particles.update(dt)

        if self.coin and self.distance_sq_2d(self.player.position, self.coin.position) <= (PLAYER_RADIUS + COIN_RADIUS)**2:
            self.score += 1
            if self.coin_sound is not None:
                try:
                    self.coin_sound.play()
                except pygame.error:
                    self.coin_sound = None
            self.particles.emit(self.coin.position + Vec3(0.0, 0.9, 0.0), COIN_GLOW, 10, (1.2, 3.2), (0.08, 0.15), (0.22, 0.52), gravity=1.8)
            self.coin = self.spawn_coin()

        if self.ghost_active and self.distance_sq_2d(self.player.position, self.ghost.position) <= (PLAYER_RADIUS * 2)**2:
            self.end_game()
            return

        for bomb in self.bombs:
            if self.distance_sq_2d(self.player.position, bomb.position) <= (PLAYER_RADIUS + BOMB_RADIUS)**2:
                self.explode_bomb(bomb)
                self.end_game()
                return

    def draw_centered_text(self, text, font, color, y):
        text_surface = font.render(text, True, color)
        text_rect = text_surface.get_rect(center=(WIDTH // 2, y))
        self.screen.blit(text_surface, text_rect)

    def draw_panel(self, rect, pulse=0.0):
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(panel, PANEL_BG, panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, (*PANEL_EDGE, 220), panel.get_rect(), 2, border_radius=18)
        band_y = int(rect.height * (0.18 + pulse * 0.08))
        pygame.draw.rect(panel, (255, 255, 255, 18), (8, band_y, rect.width - 16, 10), border_radius=5)
        self.screen.blit(panel, rect.topleft)

    def draw_hud(self):
        pulse = 0.5 + 0.5 * math.sin(self.total_time * 2.1)
        timer_surface = self.ui_font.render(f"Time {self.survival_time:05.2f}s", True, TEXT_COLOR)
        score_surface = self.ui_font.render(f"Score {self.score}", True, TEXT_COLOR)
        tip_surface = self.small_font.render("Drive: WASD / Arrows", True, (216, 226, 242))

        self.draw_panel(pygame.Rect(16, 18, 252, 86), pulse)
        self.screen.blit(timer_surface, (32, 30))
        self.screen.blit(tip_surface, (32, 61))

        score_rect = pygame.Rect(WIDTH - 212, 18, 196, 62)
        self.draw_panel(score_rect, 1.0 - pulse)
        score_text_rect = score_surface.get_rect(center=score_rect.center)
        self.screen.blit(score_surface, score_text_rect)

    def draw_start_screen(self):
        self.draw_centered_text("TIME TRAVEL RUNNER 3D", self.title_font, TEXT_COLOR, 108)
        self.draw_centered_text("Drive the neon corridor. Your past hunts you 5 seconds later.", self.small_font, TEXT_COLOR, 152)

        rules_rect = pygame.Rect(104, 182, 652, 300)
        self.draw_panel(rules_rect, 0.5 + 0.5 * math.sin(self.total_time * 2.0))
        rules = [
            "RULES",
            "Steer with LEFT / RIGHT or A / D.",
            "Accelerate with UP / W and reverse with DOWN / S.",
            "A ghost repeats your path after 5 seconds.",
            "Collect coins, avoid bombs, survive the paradox.",
            "Press SPACE to start.",
        ]
        for index, line in enumerate(rules):
            font = self.ui_font if index == 0 else self.small_font
            color = ACCENT_COLOR if index == 0 else TEXT_COLOR
            text_surface = font.render(line, True, color)
            self.screen.blit(text_surface, (rules_rect.x + 28, rules_rect.y + 24 + index * 42))

        if self.start_overlay_alpha > 0:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((4, 6, 14, int(self.start_overlay_alpha)))
            self.screen.blit(overlay, (0, 0))

    def draw_game_over_screen(self):
        pulse = 0.55 + 0.45 * math.sin(self.total_time * 3.0)
        self.draw_centered_text("TIME PARADOX", self.title_font, ACCENT_COLOR, HEIGHT // 2 - 48)
        self.draw_centered_text(
            f"Survived {self.survival_time:.2f}s   Score {self.score}",
            self.ui_font,
            TEXT_COLOR,
            HEIGHT // 2 + 8,
        )
        self.draw_centered_text("Press R to restart", self.ui_font, lerp_color(TEXT_COLOR, ACCENT_COLOR, pulse * 0.3), HEIGHT // 2 + 60)

    def draw_playfield(self):
        self.renderer.draw_background(self.total_time)
        self.renderer.draw_ground(self.total_time)
        self.renderer.draw_world_environment(self.total_time)
        self.renderer.draw_arena_bounds()

        drawables = []
        if self.coin:
            coin_proj = self.renderer.camera.project(self.coin.position)
            if coin_proj:
                drawables.append(("coin", coin_proj[3], self.coin))
        for bomb in self.bombs:
            bomb_proj = self.renderer.camera.project(bomb.position)
            if bomb_proj:
                drawables.append(("bomb", bomb_proj[3], bomb))
        player_proj = self.renderer.camera.project(self.player.position)
        if player_proj:
            drawables.append(("player", player_proj[3], self.player))
        if self.ghost_active:
            ghost_proj = self.renderer.camera.project(self.ghost.position)
            if ghost_proj:
                drawables.append(("ghost", ghost_proj[3], self.ghost))

        drawables.sort(key=lambda item: item[1], reverse=True)
        for kind, _, obj in drawables:
            if kind == "coin":
                self.renderer.draw_coin(obj, self.total_time)
            elif kind == "bomb":
                self.renderer.draw_bomb(obj, self.total_time)
            elif kind == "player":
                self.renderer.draw_player(obj, self.total_time, self.player_trail, ghost=False)
            elif kind == "ghost":
                self.renderer.draw_player(obj, self.total_time, self.ghost_trail, ghost=True)

        self.particles.draw(self.screen, self.renderer.camera, FOG_COLOR)
        self.draw_hud()

    def render(self):
        if self.state == "start":
            self.renderer.camera.update_follow(self.player.position, self.player.forward, 0.0, 1 / FPS)
            self.draw_playfield()
            self.draw_start_screen()
        elif self.state == "playing":
            self.draw_playfield()
        elif self.state == "game_over":
            self.draw_playfield()
            self.draw_game_over_screen()

        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()

            if self.state == "playing":
                self.update(dt)
            else:
                self.total_time += dt
                self.start_overlay_alpha = max(0.0, self.start_overlay_alpha - dt * 180)
                self.particles.update(dt)

            self.render()

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()