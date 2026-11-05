import Phaser from "phaser";
import type { Companion, PublicActivity, World } from "@/lib/education/schema";
import { artUrl, fieldArt, guideArt, guideFilter, landmarkArt } from "./fieldArt";

const height = 746;
const scenery = {
  fern: "sprites/helechos",
  flowers: "sprites/flores",
  stones: "sprites/piedras",
  lilies: "sprites/nenufar",
  reeds: "sprites/juncos",
  branch: "sprites/rama",
  frog: "sprites/rana",
  fish: "sprites/pez",
};

export type TrailStop = {
  id: string;
  title: string;
  type: PublicActivity["type"];
  complete: boolean;
  observation?: string;
};

export function createFieldGame({
  host,
  theme,
  stops,
  pet,
  onReady,
  onError,
  onSelect,
  onObserve,
  onNear,
}: {
  host: HTMLDivElement;
  theme: World["theme"];
  stops: TrailStop[];
  pet: Pick<Companion, "color" | "accessory">;
  onReady: () => void;
  onError: () => void;
  onSelect: (id: string) => void;
  onObserve?: (id: string) => void;
  onNear?: (id: string | null) => void;
}) {
  const art = fieldArt[theme];
  const width = Math.max(1680, 720 + (stops.length - 1) * 224);
  const ground = height * art.ground;
  const spots = stops.map((stop, i) => ({
    ...stop,
    x: 410 + (i / Math.max(1, stops.length - 1)) * (width - 750),
  }));
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  let alive = true;
  let selected = "";

  class Trail extends Phaser.Scene {
    private guide?: Phaser.GameObjects.Image;
    private accessory?: Phaser.GameObjects.Image;
    private badges = new Map<string, Phaser.GameObjects.Text>();
    private failed = false;
    private target = 255;
    private cameraX = 255;
    private winds: {
      image: Phaser.GameObjects.Image;
      angle: number;
      phase: number;
      amount: number;
    }[] = [];
    private particles: { light: Phaser.GameObjects.Arc; x: number; y: number; phase: number }[] =
      [];
    private nearby: string | null = null;
    private gaze = 255;
    private arrival: { id: string; callback: () => void; deadline: number } | null = null;

    preload() {
      this.load.on(Phaser.Loader.Events.FILE_LOAD_ERROR, () => {
        this.failed = true;
      });
      this.load.image("trail", artUrl(art.background));
      this.load.image("guide", artUrl(guideArt.ready));
      if (pet.accessory !== "none")
        this.load.image("guide-accessory", artUrl(guideArt[pet.accessory]));
      for (const file of new Set(Object.values(landmarkArt))) this.load.image(file, artUrl(file));
      for (const [name, file] of Object.entries(scenery)) this.load.image(name, artUrl(file));
    }

    private object(key: string, x: number, y: number, size: number, depth: number) {
      const image = this.add.image(x, y, key).setOrigin(0.5, 1).setDepth(depth);
      return image.setDisplaySize((image.width / image.height) * size, size);
    }

    create() {
      if (this.failed || !alive) {
        if (alive) onError();
        return;
      }
      this.add.image(0, 0, "trail").setOrigin(0).setDisplaySize(width, height);
      const panorama = this.textures.get("trail").getSourceImage() as HTMLImageElement;
      this.add
        .image(0, 0, "trail")
        .setOrigin(0)
        .setDisplaySize(width * 1.18, height)
        .setCrop(0, 0, panorama.width, panorama.height * 0.56)
        .setScrollFactor(0.82, 1)
        .setDepth(1);
      if (theme === "reserve") {
        const x = (at: number) => (at / 1680) * width;
        this.object("lilies", x(730), ground - 132, 53, 4);
        this.object("fish", x(819), ground - 146, 52, 3);
        this.object("frog", x(1227), ground - 11, 72, 7);
        this.object("stones", x(1136), ground + 33, 65, 9);
        this.object("reeds", x(1520), ground - 40, 122, 8);
        this.object("flowers", x(554), ground + 63, 86, 34).setScrollFactor(1.07, 1);
        this.object("fern", x(105), height + 14, 220, 40).setScrollFactor(1.14, 1);
        this.object("branch", x(1665), height + 22, 183, 42).setScrollFactor(1.08, 1);
      }
      const foreground = [
        this.object(
          "fern",
          width * 0.05,
          height + 30,
          theme === "space" ? 165 : 215,
          40,
        ).setScrollFactor(1.13, 1),
        this.object("branch", width * 0.65, height + 50, 176, 41).setScrollFactor(1.08, 1),
        this.object("flowers", width * 0.91, height + 25, 122, 42).setScrollFactor(1.16, 1),
      ];
      for (const [index, plant] of foreground.entries()) {
        if (theme === "space") plant.setTint(0x9aabb7);
        this.winds.push({ image: plant, angle: plant.angle, phase: index * 2, amount: 1.1 });
      }
      for (let index = 0; index < 20; index++) {
        const x = (index * 193 + 97) % Math.floor(width);
        const y =
          theme === "space" ? 65 + ((index * 83) % 240) : ground - 100 - ((index * 61) % 330);
        const light = this.add
          .circle(x, y, theme === "space" ? 1.8 : 2.2, theme === "space" ? 0xf3ecce : 0xffe7a8, 0.7)
          .setDepth(5)
          .setScrollFactor(0.9, 1);
        this.particles.push({ light, x, y, phase: index * 1.37 });
      }

      for (const [index, stop] of spots.entries()) {
        const landmark = this.object(
          landmarkArt[stop.type],
          stop.x,
          ground + 5,
          stops.length > 3 ? 148 : 172,
          15,
        );
        const scaleX = landmark.scaleX;
        const scaleY = landmark.scaleY;
        landmark.on("pointerover", () => {
          if (this.arrival) return;
          this.tweens.killTweensOf(landmark);
          if (motion.matches) landmark.setScale(scaleX * 1.04, scaleY * 1.04);
          else
            this.tweens.add({
              targets: landmark,
              scaleX: scaleX * 1.07,
              scaleY: scaleY * 1.07,
              duration: 170,
              ease: "Sine.Out",
            });
        });
        landmark.on("pointerout", () => {
          this.tweens.killTweensOf(landmark);
          landmark.setScale(scaleX, scaleY);
        });
        landmark.setInteractive({ useHandCursor: true });
        landmark.on(
          "pointerdown",
          (
            _pointer: Phaser.Input.Pointer,
            _x: number,
            _y: number,
            event: Phaser.Types.Input.EventData,
          ) => {
            event.stopPropagation();
            this.pick(stop.id);
          },
        );
        const title = stop.title.length > 36 ? `${stop.title.slice(0, 34)}…` : stop.title;
        const label = this.add
          .text(
            stop.x,
            ground - (stops.length > 3 ? 160 : 185),
            `${stop.complete ? "✓" : index + 1}   ${title}`,
            {
              fontFamily: "General Sans, system-ui, sans-serif",
              fontStyle: "bold",
              fontSize: stops.length > 3 ? "18px" : "21px",
              ...(stops.length > 3
                ? { wordWrap: { width: 168, useAdvancedWrap: true }, align: "center" }
                : {}),
              color: "#103c3e",
              backgroundColor: "#f9f5df",
              padding: { x: 10, y: 6 },
            },
          )
          .setOrigin(0.5, 1)
          .setDepth(18);
        label.setInteractive({ useHandCursor: true });
        label.on(
          "pointerdown",
          (
            _pointer: Phaser.Input.Pointer,
            _x: number,
            _y: number,
            event: Phaser.Types.Input.EventData,
          ) => {
            event.stopPropagation();
            this.pick(stop.id);
          },
        );
        this.badges.set(stop.id, label);
        if (stop.observation?.trim()) {
          const clue = this.object(
            index % 2 ? "flowers" : "stones",
            stop.x + 90,
            ground + 27,
            55,
            20,
          );
          const marker = this.add
            .circle(stop.x + 89, ground - 34, 12, 0xffe18a)
            .setDepth(21)
            .setStrokeStyle(2, 0x345c55);
          const symbol = this.add
            .text(stop.x + 89, ground - 34, "?", {
              fontFamily: "system-ui, sans-serif",
              fontSize: "16px",
              color: "#183e39",
              fontStyle: "bold",
            })
            .setOrigin(0.5)
            .setDepth(22);
          for (const item of [clue, marker, symbol]) {
            item.setInteractive({ useHandCursor: true });
            item.on(
              "pointerdown",
              (
                _pointer: Phaser.Input.Pointer,
                _x: number,
                _y: number,
                event: Phaser.Types.Input.EventData,
              ) => {
                event.stopPropagation();
                this.pick(stop.id);
                if (alive) onObserve?.(stop.id);
              },
            );
          }
          this.winds.push({ image: clue, angle: 0, phase: index * 1.2, amount: 1.8 });
        }
      }

      let guideKey = "guide";
      if (pet.color !== "sunburst") {
        const original = this.textures.get(guideKey).getSourceImage() as HTMLImageElement;
        const tint = this.textures.createCanvas("guide-color", original.width, original.height);
        if (tint) {
          tint.context.filter = guideFilter[pet.color];
          tint.context.drawImage(original, 0, 0);
          tint.refresh();
          guideKey = "guide-color";
        }
      }
      this.guide = this.object(guideKey, this.target, ground + 19, 124, 28);
      if (pet.accessory !== "none")
        this.accessory = this.object(
          "guide-accessory",
          this.target,
          ground - 11,
          pet.accessory === "scarf" ? 28 : 31,
          29,
        );
      const resize = () => this.frameCamera();
      this.scale.on(Phaser.Scale.Events.RESIZE, resize);
      this.events.once(Phaser.Scenes.Events.SHUTDOWN, () =>
        this.scale.off(Phaser.Scale.Events.RESIZE, resize),
      );
      this.input.on("pointerdown", (pointer: Phaser.Input.Pointer) => this.walk(pointer.worldX));
      this.input.on("pointermove", (pointer: Phaser.Input.Pointer) => {
        this.gaze = pointer.worldX;
      });
      if (!motion.matches) this.cameras.main.fadeIn(260, 15, 45, 42);
      this.frameCamera();
      if (alive) onReady();
    }

    private frameCamera() {
      const camera = this.cameras.main;
      camera.setZoom(Math.max(this.scale.width / width, this.scale.height / height));
      camera.setBounds(0, 0, width, height);
      camera.centerOn(this.cameraX, height / 2);
    }

    private walk(x: number) {
      if (this.arrival) return;
      this.target = Phaser.Math.Clamp(x, 76, width - 76);
    }

    step(direction: number) {
      this.walk(this.target + direction * 212);
    }

    pick(id: string) {
      const spot = spots.find((entry) => entry.id === id);
      if (!spot) return;
      this.walk(spot.x - 98);
      if (selected) this.badges.get(selected)?.setBackgroundColor("#f9f5df");
      selected = id;
      this.badges.get(id)?.setBackgroundColor("#ffd35a");
      if (alive) onSelect(id);
    }

    enter(id: string, callback: () => void) {
      if (this.arrival || !this.guide) return;
      const stop = spots.find((item) => item.id === id);
      if (!stop) return;
      if (motion.matches) {
        callback();
        return;
      }
      this.target = stop.x - 98;
      this.arrival = { id, callback, deadline: this.time.now + 1100 };
    }

    override update(time: number, delta: number) {
      if (!this.guide) return;
      const difference = this.target - this.guide.x;
      const walking = Math.abs(difference) > 1;
      if (walking) this.guide.setFlipX(difference < 0);
      const step = motion.matches
        ? Math.abs(difference)
        : Math.min((420 * Math.min(delta, 40)) / 1000, Math.abs(difference));
      const x = this.guide.x + Math.sign(difference) * step;
      const bounce = motion.matches
        ? 0
        : walking
          ? Math.abs(Math.sin(time / 80)) * 6
          : Math.sin(time / 550) * 1.7;
      this.guide.setPosition(x, ground + 19 - bounce);
      if (!walking) {
        this.guide.setFlipX(this.gaze < x);
        this.guide.setAngle(motion.matches ? 0 : Phaser.Math.Clamp((this.gaze - x) * 0.009, -3, 3));
      } else this.guide.setAngle(0);
      if (this.accessory)
        this.accessory.setPosition(
          x + (pet.accessory === "star" ? 31 : 0),
          ground - (pet.accessory === "star" ? 45 : 15) - bounce,
        );
      this.cameraX = motion.matches
        ? x
        : this.cameraX + (x - this.cameraX) * Math.min(1, delta / 120);
      this.cameras.main.centerOn(this.cameraX, height / 2);
      if (!motion.matches) {
        for (const plant of this.winds)
          plant.image.setAngle(plant.angle + Math.sin(time / 1400 + plant.phase) * plant.amount);
        for (const particle of this.particles) {
          particle.light.setAlpha(0.35 + (Math.sin(time / 900 + particle.phase) + 1) * 0.26);
          if (theme !== "space")
            particle.light.setPosition(
              particle.x + Math.sin(time / 2400 + particle.phase) * 16,
              particle.y + Math.sin(time / 1800 + particle.phase) * 10,
            );
        }
      }
      const near = spots.find((stop) => Math.abs(stop.x - 98 - x) < 145)?.id ?? null;
      if (near !== this.nearby) {
        this.nearby = near;
        if (alive) onNear?.(near);
      }
      if (this.arrival && (!walking || time >= this.arrival.deadline)) {
        const destination = this.arrival;
        this.arrival = null;
        this.cameras.main.once(Phaser.Cameras.Scene2D.Events.FADE_OUT_COMPLETE, () => {
          if (alive) {
            destination.callback();
            this.cameras.main.fadeIn(180, 14, 46, 43);
          }
        });
        this.cameras.main.fadeOut(180, 14, 46, 43);
      }
    }
  }

  const scene = new Trail();
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent: host,
    backgroundColor: "#103c3e",
    scene,
    scale: { mode: Phaser.Scale.RESIZE, width: host.clientWidth, height: host.clientHeight },
    input: { keyboard: false, gamepad: false },
    render: { antialias: true, roundPixels: true },
    audio: { noAudio: true },
    fps: { limit: 60 },
    banner: false,
  });
  game.canvas?.setAttribute("aria-hidden", "true");
  return {
    step: (direction: number) => scene.step(direction),
    pick: (id: string) => scene.pick(id),
    enter: (id: string, callback: () => void) => scene.enter(id, callback),
    destroy: () => {
      alive = false;
      game.destroy(true);
    },
  };
}
