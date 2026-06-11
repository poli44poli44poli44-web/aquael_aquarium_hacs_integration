var _temp = loadHeaterSettings(heaterFunctions.heaterSettings());
var _percent;
var _currentTemp;
var knobEnabled = false;
var number = _temp;
var numberPrev = number;
var $body = $("body");
var $delay;
var intervalId, intervalId2;
var _data;
var _data2;
var isFahrenheit;
var isFirstLoad = true;
var checkPowerFunctions = setInterval(function() {
    if (typeof heaterFunctions !== "undefined") {
        clearInterval(checkPowerFunctions);
        console.log("heaterFunctions zosta\u0142o zdefiniowane");
        var lang = heaterFunctions.getDeviceLang();
        document.getElementById("LangElement").lang = lang;
        console.log("lang");
        console.log(lang);
        vueInstance.updateTemperatureUnit();
        iosRefresh();

    } else {
        console.log("czekam na za\u0142adowanie heaterFunctions...");
    }
}, 100);

var InputSpinner = {
    name: "InputSpinner",
    template: '\n      <div\n        class="input-spinner"\n        :class="{\'is-dragging\': dragging }"\n      >\n        <div\n          class="input-spinner__track u-flex-center"\n          :class="{\'is-min\': isMin, \'is-max\': isMax }"\n        >\n          <svg class="input-spinner__icon input-spinner__icon--minus" version="1.1" xmlns="http://www.w3.org/2000/svg" width="640" height="640" viewBox="0 0 640 640">\n            <path d="M512 320c0 17.696-1.536 32-19.232 32h-345.536c-17.664 0-19.232-14.304-19.232-32s1.568-32 19.232-32h345.568c17.664 0 19.2 14.304 19.2 32z"></path>\n          </svg>\n          <div\n            class="input-spinner__knob u-flex-center"\n            ref="knob"\n          >\n            <span>{{value}}</span>\n          </div>\n          <svg class="input-spinner__icon input-spinner__icon--plus" version="1.1" xmlns="http://www.w3.org/2000/svg" width="768" height="768" viewBox="0 0 768 768">\n            <path d="M607.5 415.5h-192v192h-63v-192h-192v-63h192v-192h63v192h192v63z"></path>\n          </svg>\n        </div>\n        <div class="input-spinner__ball u-flex-center">\n          <svg class="input-spinner__ball-bg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 695.5"><title>drop</title><path d="M587.75,523.75,384,727.5,180.25,523.75a281.43,281.43,0,0,1-62.87-94.5,289.88,289.88,0,0,1,0-218.5A289.43,289.43,0,0,1,274.75,53.5a288.32,288.32,0,0,1,218.5,0A288.37,288.37,0,0,1,650.5,210.88a288.43,288.43,0,0,1-62.75,312.88Z" transform="translate(-96 -32)"/></svg>\n          <transition-group\n            :name="transitionName"\n            tag="div"\n            class="input-spinner__values u-flex-center"\n          >\n            <span v-for="item in activeValue" :key="item">\n              {{ item }}\n            </span>\n          </transition-group>\n        </div>\n      </div>\n    ',
    props: {
        defaultValue: {
            type: Number,
            "default": number

        },
        min: {
            type: Number,
            "default": _temp
        },
        max: {
            type: Number,
            "default": 33
        },
        timerStep: {
            type: Number,
            "default": 1
        },
        interval: {
            type: Number,
            "default": 1000
        },
        thresholds: {
            type: Array,
            "default": [{
                threshold: 30,
                value: 1
            }, {
                threshold: 100,
                value: 10
            }]
        }
    },
    data: function() {
        return {
            value: this.defaultValue,
            dragging: false,
            position: 0,
            activeValue: [0],
            transitionName: "list",
            initialInterval: 1500
        };
    },
    mounted: function() {
        this.width = this.$el.getBoundingClientRect().width;
        this.halfWidth = this.width / 2;
        this.knobWidth = this.$refs.knob.getBoundingClientRect().width;
        this.knobWidthHalf = this.knobWidth / 2;
        this.$refs.knob.addEventListener("mousedown", this.onStart);
        this.$refs.knob.addEventListener("touchstart", this.onStart);
        window.addEventListener("mousemove", this.onMove);
        window.addEventListener("touchmove", this.onMove);
        window.addEventListener("mouseup", this.onEnd);
        window.addEventListener("touchend", this.onEnd);
    },
    beforeDestroy: function() {
        this.$refs.knob.removeEventListener("mousedown", this.onStart);
        this.$refs.knob.addEventListener("touchstart", this.onStart);
        window.removeEventListener("mousemove", this.onMove);
        window.removeEventListener("touchmove", this.onMove);
        window.removeEventListener("mouseup", this.onEnd);
        window.removeEventListener("touchend", this.onEnd);
    },
    watch: {
        "position": function(val, oldVal) {
            if (this.position <= 100) {
                this.transitionName = val > oldVal ? "list" : "list--reverse";
            }
        }
    },
    methods: {
        onStart: function(e) {
            this.dragging = true;
            this.startX = this.getScreenX(e);
        },
        onEnd: function(e) {
            var deltaX = this.getScreenX(e) - this.startX;
            var position = this.positionPercent(deltaX);
            var newValue = this.value + this.activeValue[0];
            if (this.dragging) {
                this.value = newValue;
                if (newValue > this.max) {
                    this.value = this.max;
                }
                if (newValue < this.min) {
                    this.value = this.min;
                }
            }
            this.$emit("update", this.value);
            this.setPosition(0);
            this.dragging = false;
        },
        onMove: function(e) {
            if (this.dragging) {
                var deltaXFromCenter = this.getScreenX(e) - this.startX;
                this.setPosition(deltaXFromCenter);
            }
        },
        setPosition: function(deltaXFromCenter) {
            this.position = this.positionPercent(deltaXFromCenter);
            if (Math.abs(this.position) >= 100 && !this.timerEnabled) {
                this.timerEnabled = true;
                this.setActiveValue(this.getThresholdValue(this.position));
                this.startTimer(this.position);
            }
            if (Math.abs(this.position) < 100) {
                this.timerEnabled = false;
            }
            if (deltaXFromCenter <= this.halfWidth && deltaXFromCenter >= -this.halfWidth) {
                this.setActiveValue(this.getThresholdValue(this.position));
                this.$el.style.setProperty("--position", Math.round(deltaXFromCenter) + "px");
            }
        },
        setActiveValue: function(val) {
            this.activeValue = [val];
        },
        startTimer: function() {
            var $jscomp$this = this;
            if (this.timer) {
                clearTimeout(this.timer);
            }
            this.timer = setTimeout(function() {
                if ($jscomp$this.timerEnabled) {
                    var newValue = $jscomp$this.position >= 0 ? $jscomp$this.activeValue[0] + $jscomp$this.timerStep : $jscomp$this.activeValue[0] - $jscomp$this.timerStep;
                    $jscomp$this.setActiveValue(newValue);
                    $jscomp$this.startTimer();
                }
            }, this.interval);
        },
        positionPercent: function(deltaXFromCenter) {
            return deltaXFromCenter / this.halfWidth * 100;
        },
        getThresholdValue: function(val) {
            var availableValues = this.thresholds.filter(function(item) {
                return item.threshold <= Math.abs(Math.round(val));
            });
            var value = 0;
            if (availableValues.length > 0) {
                value = availableValues.pop().value;
            }
            return val >= 0 ? value : -1 * value;
        },
        getScreenX: function(e) {
            if (e.changedTouches) {
                return e.changedTouches[0].screenX;
            }
            return e.screenX;
        }
    },
    computed: {
        isMin: function() {
            return this.value <= this.min;
        },
        isMax: function() {
            return this.value >= this.max;
        }
    }
};

const vueInstance = new Vue({
    el: "#app",
    components: {
        InputSpinner: InputSpinner
    },
    data: {
        currentTemp: _currentTemp,
        topHeaterPower: _percent,
        currentVal: _temp,
        currentValUnit: '\u2103',
        min: 20,
        max: 33,
        interval: 1000,
        timerStep: 5,
        thresholds: [{
            threshold: 30,
            value: 0.1
        }, {
            threshold: 100,
            value: 1
        }]
    },
    methods: {
        roundToDecimal(number, decimals) {
            return number.toFixed(decimals);
        },
        updateTemperatureUnit() {
            console.log("updateTemperatureUnit()");

            this.currentValUnit = isFahrenheit ? '\u2109' : '\u2103';
            this.min = isFahrenheit ? celsiusToFahrenheit(20) : 20;
            this.max = isFahrenheit ? celsiusToFahrenheit(33) : 33;
            loadHeaterSettings(heaterFunctions.heaterSettings());
            this.updateValue(_temp);
        },
        updateAllValue: function(updateCurrentTemp, updateProcent, updatetemp) {
            this.currentTemp = updateCurrentTemp;
            this.topHeaterPower = updateProcent;
        },
        updateValue: function(val) {
            console.log("updateValue()");
            this.currentVal = val;
            number = val;
            if (number !== numberPrev) {
                iosUpdate();
                numberPrev = number;
            }
        },
        changeThreshold: function(thresholdIndex, evt) {
            this.thresholds = this.thresholds.map(function(item, index) {
                if (thresholdIndex === index) {
                    return {
                        threshold: evt.target.value,
                        value: item.value
                    };
                }
                return item;
            });
        },
        changeThresholdValue: function(thresholdIndex, evt) {
            this.thresholds = this.thresholds.map(function(item, index) {
                if (thresholdIndex === index) {
                    return {
                        threshold: item.threshold,
                        value: evt.target.value
                    };
                }
                return item;
            });
        }
    }
});

$(document).ready(function() {
    var currentLang = "pl";
    var appContent = document.querySelector(".app__content#IDapp__content");
    appContent.style.display = "none";
    knobEnabled = heaterFunctions.isHeaterOn();
    $(".toggle input").prop("checked", knobEnabled);
    if (knobEnabled) {
        $("#IDapp__content").show();
        console.log("IDapp__content.show();");
    } else {
        $("#IDapp__content").hide();
        console.log("IDapp__content.hide();");
    }
    setTextVisable();
    $(".toggle input").change(function(a) {
        console.log("toggle input");
        knobEnabled = $(this).is(":checked");
        if ($(this).prop("checked")) {
            $("#IDapp__content").show();
            console.log("IDapp__content.show();");
        } else {
            $("#IDapp__content").hide();
            console.log("IDapp__content.hide();");
        }
        iosUpdate();
        setTextVisable();
    });

    if (heaterFunctions.isPumpEnabled()) {
        $("#pump-off-warning").css("visibility", "hidden");
    } else {
        $("#pump-off-warning").css("visibility", "visible");
    }

});

function setTextVisable() {
    if ($("#IDapp__content").is(":visible")) {
        $("#text-visability").hide();
        $("#text-visability2").show();
        $("#IDapp__content").show();
        console.log("pump `on");
    } else {
        $("#text-visability").show();
        $("#text-visability2").hide();
        $("#IDapp__content").hide();
        try {
            clearInterval(intervalId);
            clearInterval(intervalId2);
        } catch (e$0) {
            console.log("error B");
        }
        console.log("gray!");
    }
}

function iosUpdate() {
    window.webkit.messageHandlers.saveTemperature.postMessage({
        "temperature": (isFahrenheit ? fahrenheitToCelsius(number) : number) + "",
        "isOn": knobEnabled + ""
    })
}

function iosRefresh() {
    setInterval(function() {
        window.webkit.messageHandlers.updateUserScript.postMessage("update")
        console.log("Refresh");
    }, 2500);
}

function celsiusToFahrenheit(celsius) {
    return celsius * 1.8 + 32;
}

function fahrenheitToCelsius(fahrenheit) {
    return (5 * (fahrenheit - 32.0)) / 9.0;
}

function loadHeaterSettings(hs) {
    console.log(hs);
    if (hs == null || hs === '' || hs === '{}') {
        return;
    }
    _data = JSON.parse(hs);
    console.log('parsed2: ' + JSON.stringify(_data));
    isFahrenheit = heaterFunctions.getTemperatureUnit() === 'F';
    var pt = isFahrenheit ? celsiusToFahrenheit(_data.setTemperature) : _data.setTemperature;
    console.log('temperature: ' + pt);
    _temp = pt;
    console.log("water ok ", _data.waterSensorFlooded);
    console.log('_temp: ' + _temp);
    if (!_data.waterSensorFlooded) {
        $("#water-level-warning").show();
        console.log("#water-level-warningsShow()");
    } else {
        $("#water-level-warning").hide();
        console.log("#water-level-warningsHide()");
    }
    if (!_data.heaterOutput) {
        $("#heater-work-icon").css("visibility", "hidden");
    } else {
        $("#heater-work-icon").css("visibility", "visible");
    }

    _percent = _data.TopHeaterPower;
    console.log("_percent: ", _percent);
    _currentTemp = isFahrenheit ? celsiusToFahrenheit(_data.measuredTemp) : _data.measuredTemp;
    return pt
}

function onJsonReceived(json) {
    console.log("Received JSON: " + json);
    let jsonString = json.replace(/^Optional\("?|"?\)?$/g, '').replace(/^'|'$/g, '');
    const obj = JSON.parse(jsonString);
    const measuredTemp = obj.measuredTemp;
    const heaterOutput = obj['heaterOutput'];
    const waterSensorFlooded = obj.waterSensorFlooded;
    _currentTemp = isFahrenheit ? celsiusToFahrenheit(obj.measuredTemp) : obj.measuredTemp;
    _temp = isFahrenheit ? celsiusToFahrenheit(obj.setTemperature) : obj.setTemperature;
    _percent = obj.TopHeaterPower;
    vueInstance.updateAllValue(_currentTemp, _percent, _temp);
    if (!obj.heaterOutput) {
        $("#heater-work-icon").css("visibility", "hidden");
    } else {
        $("#heater-work-icon").css("visibility", "visible");
    }

    console.log("obj.pumpEnabled: " + obj.pumpEnabled);
    if (obj.pumpEnabled) {
        $("#pump-off-warning").css("visibility", "hidden");
    } else {
        $("#pump-off-warning").css("visibility", "visible");
    }

}

setTextVisable();
