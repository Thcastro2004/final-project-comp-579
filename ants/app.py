from ants.config import (
    BORDER_LOCK,
    FOOD_R_MAX_FRAC,
    SIM_SPEED_PRESETS,
    TERRAIN_WALL,
    PANEL_MARGIN,
    PANEL_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.fonts import make_ui_fonts
from ants.persistence.session import session_read
from ants.persistence.terrain import terrain_blit_file_into, terrain_candidate_paths
from ants.ui.drawMap import draw_map_view, update_food_paint_while_held
from ants.ui import reward_chart_window
from ants.ui.drawModals import draw_modals
from ants.ui.drawPanel import draw_panel_and_cards
from ants.ui.helpers import clamp_scroll
from ants.ui.input import process_events
from ants.ui.session_merge import init_game_state_from_session
from ants.simulation import ensure_pheromone_field, init_ants_from_state, sim_step
from ants.ui.sprites import load_ant_walk_tint_cache, load_colony_sprites, load_food_sprites
from ants.ui.state import PanelLayout, RuntimeBundle, UiTheme
from ants.world import Viewport, World


def run_window() -> int:
    import pygame

    reward_chart_window.preinit_before_pygame()

    world = World(WORLD_WIDTH, WORLD_HEIGHT)
    world_w = WINDOW_WIDTH - PANEL_WIDTH
    viewport = Viewport(
        world,
        WINDOW_WIDTH,
        WINDOW_HEIGHT,
        margin=20,
        content_rect=(0, 0, world_w, WINDOW_HEIGHT),
    )
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Ant colony sim")
    clock = pygame.time.Clock()
    font, font_small, font_title = make_ui_fonts()

    food_sprite, food_cursor_sprite = load_food_sprites(pygame)
    colony_sprites, colony_base_sprite, _ = load_colony_sprites(pygame)
    ant_walk_cache = load_ant_walk_tint_cache(pygame)

    map_rx, map_ry, map_rw, map_rh = viewport.world_rect_screen()
    terrain_surf = pygame.Surface((map_rw, map_rh))
    terrain_surf.fill(TERRAIN_WALL)

    for _tp in terrain_candidate_paths():
        if _tp.is_file() and terrain_blit_file_into(_tp, pygame, terrain_surf, map_rw, map_rh):
            break

    _ed_w = max(0, map_rw - 2 * BORDER_LOCK)
    _ed_h = max(0, map_rh - 2 * BORDER_LOCK)
    editable_inner = pygame.Rect(BORDER_LOCK, BORDER_LOCK, _ed_w, _ed_h)
    food_r_max_px = max(8.0, min(map_rw, map_rh) * FOOD_R_MAX_FRAC)

    theme = UiTheme()

    sd = session_read()
    state = init_game_state_from_session(sd)

    panel_x = world_w
    btn_h = 32
    row1_y = 44
    row2_y = row1_y + btn_h + 8
    edit_done_y = 46
    edit_brush_y = edit_done_y + btn_h + 12
    speed_btn_h = 26
    speed_label_y = row2_y + btn_h + 10
    speed_row_y = speed_label_y + 14
    col_label_y = speed_row_y + speed_btn_h + 12
    add_btn_h = 30
    add_y = col_label_y + 22
    scroll_y0 = add_y + add_btn_h + 8
    scroll_rect = pygame.Rect(
        panel_x + PANEL_MARGIN,
        scroll_y0,
        PANEL_WIDTH - 2 * PANEL_MARGIN,
        WINDOW_HEIGHT - scroll_y0 - PANEL_MARGIN,
    )

    map_screen_rect = pygame.Rect(map_rx, map_ry, map_rw, map_rh)
    nest_pick_r = max(
        22.0,
        (colony_base_sprite.get_width() * 0.5) if colony_base_sprite is not None else 28.0,
    )

    panel = PanelLayout(
        panel_x=panel_x,
        world_w=world_w,
        scroll_rect=scroll_rect,
        map_rx=map_rx,
        map_ry=map_ry,
        map_rw=map_rw,
        map_rh=map_rh,
        map_screen_rect=map_screen_rect,
        editable_inner=editable_inner,
        food_r_max_px=food_r_max_px,
        nest_pick_r=nest_pick_r,
        row1_y=row1_y,
        row2_y=row2_y,
        btn_h=btn_h,
        speed_label_y=speed_label_y,
        speed_row_y=speed_row_y,
        speed_btn_h=speed_btn_h,
        col_label_y=col_label_y,
        add_y=add_y,
        add_btn_h=add_btn_h,
        edit_done_y=edit_done_y,
        edit_brush_y=edit_brush_y,
    )

    clamp_scroll(state, panel)

    bundle = RuntimeBundle(
        pygame=pygame,
        screen=screen,
        clock=clock,
        font=font,
        font_small=font_small,
        font_title=font_title,
        world=world,
        viewport=viewport,
        terrain_surf=terrain_surf,
        theme=theme,
        panel=panel,
        food_sprite=food_sprite,
        food_cursor_sprite=food_cursor_sprite,
        colony_sprites=colony_sprites,
        ant_walk_cache=ant_walk_cache,
    )

    last_ticks: int | None = None
    was_sim_running = False

    while state.running:
        process_events(pygame, bundle, state)
        now_ticks = pygame.time.get_ticks()
        dt_ms = 16 if last_ticks is None else max(0, now_ticks - last_ticks)
        last_ticks = now_ticks

        if state.sim_running and not was_sim_running:
            ensure_pheromone_field(state, bundle)
            state.pheromone.reset()
            init_ants_from_state(state, now_ticks)
            reward_chart_window.reset_for_new_sim()

        was_sim_running = state.sim_running

        if state.sim_running and not state.sim_paused and not state.edit_map:
            speed_mult = SIM_SPEED_PRESETS[state.sim_speed_index]
            sim_step(pygame, bundle, state, int(dt_ms * speed_mult), now_ticks)
            if len(state.reward_chart_series) == len(state.ants):
                for i, ant in enumerate(state.ants):
                    state.reward_chart_series[i].append((now_ticks, ant.lifetime_return))

        state.mouse_xy = pygame.mouse.get_pos()
        update_food_paint_while_held(pygame, bundle, state)
        draw_map_view(pygame, bundle, state)
        draw_panel_and_cards(pygame, bundle, state)
        draw_modals(pygame, bundle, state)
        pygame.display.flip()
        reward_chart_window.tick(state, now_ticks)
        clock.tick(60)

    from ants.ui.map_tools import save_terrain_and_session

    save_terrain_and_session(pygame, terrain_surf, state)
    reward_chart_window.shutdown()
    pygame.quit()
    return 0
