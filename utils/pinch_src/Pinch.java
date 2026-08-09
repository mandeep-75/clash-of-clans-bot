import java.lang.reflect.Array;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

/**
 * Multi-touch pinch injector for non-rooted devices.
 *
 * ADB's {@code input} command cannot inject multi-touch gestures, and writing
 * to /dev/input requires root. This helper replicates what scrcpy-server does:
 * it is pushed to /data/local/tmp and started through {@code app_process}, so
 * it runs as the shell user (uid 2000), which is granted the hidden
 * {@code INJECT_EVENTS} permission. It then calls
 * {@code InputManager.injectInputEvent()} with a two-finger MotionEvent.
 *
 * The Android framework classes are only referenced via reflection so the
 * class compiles with a plain JDK (no android.jar needed).
 *
 * Usage:
 *   Pinch <sx1> <sy1> <sx2> <sy2> <ex1> <ey1> <ex2> <ey2> <steps> [duration_ms]
 *
 * Fingers start at (sx1, sy1) / (sx2, sy2) and move linearly to
 * (ex1, ey1) / (ex2, ey2) over {@code steps} frames.
 */
public class Pinch {

    private static final int SOURCE_TOUCHSCREEN = 0x1002;
    private static final int TOOL_TYPE_FINGER = 1;

    private static final int ACTION_DOWN = 0;
    private static final int ACTION_UP = 1;
    private static final int ACTION_MOVE = 2;
    private static final int ACTION_POINTER_DOWN = 5;
    private static final int ACTION_POINTER_UP = 6;
    private static final int ACTION_POINTER_INDEX_SHIFT = 8;

    private static final int INJECT_ASYNC = 0;

    private static Method injectMethod;
    private static Object inputManager;
    private static Method obtainMethod;
    private static Method uptimeMethod;
    private static ConstructorHolder coords;
    private static ConstructorHolder props;

    private static final class ConstructorHolder {
        private final java.lang.reflect.Constructor<?> ctor;
        private final Field[] fields;

        ConstructorHolder(String className, String[] fieldNames) throws Exception {
            Class<?> cls = Class.forName(className);
            ctor = cls.getConstructor();
            fields = new Field[fieldNames.length];
            for (int i = 0; i < fieldNames.length; i++) {
                fields[i] = cls.getField(fieldNames[i]);
            }
        }

        Object newInstance() throws Exception {
            return ctor.newInstance();
        }

        void set(Object instance, String fieldName, float value) throws Exception {
            for (Field f : fields) {
                if (f.getName().equals(fieldName)) {
                    f.setFloat(instance, value);
                    return;
                }
            }
            throw new NoSuchFieldException(fieldName);
        }

        void setInt(Object instance, String fieldName, int value) throws Exception {
            for (Field f : fields) {
                if (f.getName().equals(fieldName)) {
                    f.setInt(instance, value);
                    return;
                }
            }
            throw new NoSuchFieldException(fieldName);
        }
    }

    public static void main(String[] args) {
        if (args.length < 9) {
            System.err.println(
                "usage: Pinch sx1 sy1 sx2 sy2 ex1 ey1 ex2 ey2 steps [duration_ms]");
            System.exit(1);
        }
        try {
            int sx1 = Integer.parseInt(args[0]);
            int sy1 = Integer.parseInt(args[1]);
            int sx2 = Integer.parseInt(args[2]);
            int sy2 = Integer.parseInt(args[3]);
            int ex1 = Integer.parseInt(args[4]);
            int ey1 = Integer.parseInt(args[5]);
            int ex2 = Integer.parseInt(args[6]);
            int ey2 = Integer.parseInt(args[7]);
            int steps = Integer.parseInt(args[8]);
            int duration = args.length > 9 ? Integer.parseInt(args[9]) : 300;
            init();
            pinch(sx1, sy1, sx2, sy2, ex1, ey1, ex2, ey2, steps, duration);
            System.out.println("pinch ok");
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(2);
        }
    }

    private static void init() throws Exception {
        Class<?> inputManagerClass = Class.forName("android.hardware.input.InputManager");
        Method getInstance = inputManagerClass.getMethod("getInstance");
        inputManager = getInstance.invoke(null);
        injectMethod = inputManagerClass.getMethod(
            "injectInputEvent",
            Class.forName("android.view.InputEvent"),
            int.class);

        obtainMethod = Class.forName("android.view.MotionEvent").getMethod(
            "obtain",
            long.class, long.class, int.class, int.class,
            Class.forName("android.view.MotionEvent$PointerProperties").arrayType(),
            Class.forName("android.view.MotionEvent$PointerCoords").arrayType(),
            int.class, int.class, float.class, float.class,
            int.class, int.class, int.class, int.class);

        uptimeMethod = Class.forName("android.os.SystemClock").getMethod("uptimeMillis");

        coords = new ConstructorHolder(
            "android.view.MotionEvent$PointerCoords",
            new String[]{"x", "y", "pressure"});
        props = new ConstructorHolder(
            "android.view.MotionEvent$PointerProperties",
            new String[]{"id", "toolType"});
    }

    private static long now() throws Exception {
        return (Long) uptimeMethod.invoke(null);
    }

    private static Object event(int action, long downTime, long eventTime,
                                int[] xs, int[] ys) throws Exception {
        int n = xs.length;
        Object propArr = Array.newInstance(
            Class.forName("android.view.MotionEvent$PointerProperties"), n);
        Object coordArr = Array.newInstance(
            Class.forName("android.view.MotionEvent$PointerCoords"), n);

        for (int i = 0; i < n; i++) {
            Object p = props.newInstance();
            props.setInt(p, "id", i);
            props.setInt(p, "toolType", TOOL_TYPE_FINGER);
            Array.set(propArr, i, p);

            Object c = coords.newInstance();
            coords.set(c, "x", xs[i]);
            coords.set(c, "y", ys[i]);
            coords.set(c, "pressure", 1.0f);
            Array.set(coordArr, i, c);
        }

        return obtainMethod.invoke(
            null, downTime, eventTime, action, n, propArr, coordArr,
            0, 0, 1.0f, 1.0f, 0, 0, SOURCE_TOUCHSCREEN, 0);
    }

    private static void inject(Object motionEvent) throws Exception {
        Object ok = injectMethod.invoke(inputManager, motionEvent, INJECT_ASYNC);
        if (Boolean.FALSE.equals(ok)) {
            throw new IllegalStateException("injectInputEvent returned false");
        }
    }

    private static void pinch(int sx1, int sy1, int sx2, int sy2,
                              int ex1, int ey1, int ex2, int ey2,
                              int steps, int duration) throws Exception {
        long downTime = now();

        inject(event(ACTION_DOWN, downTime, downTime,
                     new int[]{sx1}, new int[]{sy1}));
        Thread.sleep(16);

        int pointerDown = ACTION_POINTER_DOWN | (1 << ACTION_POINTER_INDEX_SHIFT);
        long t0 = now();
        inject(event(pointerDown, downTime, t0,
                     new int[]{sx1, sx2}, new int[]{sy1, sy2}));

        for (int i = 1; i <= steps; i++) {
            float t = (float) i / steps;
            int ax = Math.round(sx1 + (ex1 - sx1) * t);
            int ay = Math.round(sy1 + (ey1 - sy1) * t);
            int bx = Math.round(sx2 + (ex2 - sx2) * t);
            int by = Math.round(sy2 + (ey2 - sy2) * t);
            long ts = t0 + (long) (duration * t);
            inject(event(ACTION_MOVE, downTime, ts,
                         new int[]{ax, bx}, new int[]{ay, by}));
            Thread.sleep(Math.max(0, ts - now()));
        }

        long tEnd = t0 + duration;
        int pointerUp = ACTION_POINTER_UP | (1 << ACTION_POINTER_INDEX_SHIFT);
        inject(event(pointerUp, downTime, tEnd,
                     new int[]{ex1, ex2}, new int[]{ey1, ey2}));
        inject(event(ACTION_UP, downTime, tEnd,
                     new int[]{ex1}, new int[]{ey1}));
    }
}
