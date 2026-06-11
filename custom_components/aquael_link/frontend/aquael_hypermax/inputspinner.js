var InputSpinner = {name:"InputSpinner", template:'\n      <div\n        class="input-spinner"\n        :class="{\'is-dragging\': dragging }"\n      >\n        <div\n          class="input-spinner__track u-flex-center"\n          :class="{\'is-min\': isMin, \'is-max\': isMax }"\n        >\n          <svg class="input-spinner__icon input-spinner__icon--minus" version="1.1" xmlns="http://www.w3.org/2000/svg" width="640" height="640" viewBox="0 0 640 640">\n            <path d="M512 320c0 17.696-1.536 32-19.232 32h-345.536c-17.664 0-19.232-14.304-19.232-32s1.568-32 19.232-32h345.568c17.664 0 19.2 14.304 19.2 32z"></path>\n          </svg>\n          <div\n            class="input-spinner__knob u-flex-center"\n            ref="knob"\n          >\n            <span>{{value}}</span>\n          </div>\n          <svg class="input-spinner__icon input-spinner__icon--plus" version="1.1" xmlns="http://www.w3.org/2000/svg" width="768" height="768" viewBox="0 0 768 768">\n            <path d="M607.5 415.5h-192v192h-63v-192h-192v-63h192v-192h63v192h192v63z"></path>\n          </svg>\n        </div>\n        <div class="input-spinner__ball u-flex-center">\n          <svg class="input-spinner__ball-bg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 695.5"><title>drop</title><path d="M587.75,523.75,384,727.5,180.25,523.75a281.43,281.43,0,0,1-62.87-94.5,289.88,289.88,0,0,1,0-218.5A289.43,289.43,0,0,1,274.75,53.5a288.32,288.32,0,0,1,218.5,0A288.37,288.37,0,0,1,650.5,210.88a288.43,288.43,0,0,1-62.75,312.88Z" transform="translate(-96 -32)"/></svg>\n          <transition-group\n            :name="transitionName"\n            tag="div"\n            class="input-spinner__values u-flex-center"\n          >\n            <span v-for="item in activeValue" :key="item">\n              {{ item }}\n            </span>\n          </transition-group>\n        </div>\n      </div>\n    ',
props:{defaultValue:{type:Number, "default":powerFunctions.getCurrentPower()}, min:{type:Number, "default":50}, max:{type:Number, "default":100}, timerStep:{type:Number, "default":1}, interval:{type:Number, "default":1000}, thresholds:{type:Array, "default":[{threshold:30, value:1}, {threshold:100, value:10}]}}, data:function() {
  return {value:this.defaultValue, dragging:false, position:0, activeValue:[0], transitionName:"list", initialInterval:1500};
}, mounted:function() {
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
}, beforeDestroy:function() {
  this.$refs.knob.removeEventListener("mousedown", this.onStart);
  this.$refs.knob.addEventListener("touchstart", this.onStart);
  window.removeEventListener("mousemove", this.onMove);
  window.removeEventListener("touchmove", this.onMove);
  window.removeEventListener("mouseup", this.onEnd);
  window.removeEventListener("touchend", this.onEnd);
}, watch:{"position":function(val, oldVal) {
  if (this.position <= 100) {
    this.transitionName = val > oldVal ? "list" : "list--reverse";
  }
}}, methods:{onStart:function(e) {
  this.dragging = true;
  this.startX = this.getScreenX(e);
}, onEnd:function(e) {
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
}, onMove:function(e) {
  if (this.dragging) {
    var deltaXFromCenter = this.getScreenX(e) - this.startX;
    this.setPosition(deltaXFromCenter);
  }
}, setPosition:function(deltaXFromCenter) {
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
}, setActiveValue:function(val) {
  this.activeValue = [val];
}, startTimer:function() {
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
}, positionPercent:function(deltaXFromCenter) {
  return deltaXFromCenter / this.halfWidth * 100;
}, getThresholdValue:function(val) {
  var availableValues = this.thresholds.filter(function(item) {
    return item.threshold <= Math.abs(Math.round(val));
  });
  var value = 0;
  if (availableValues.length > 0) {
    value = availableValues.pop().value;
  }
  return val >= 0 ? value : -1 * value;
}, getScreenX:function(e) {
  if (e.changedTouches) {
    return e.changedTouches[0].screenX;
  }
  return e.screenX;
}}, computed:{isMin:function() {
  return this.value <= this.min;
}, isMax:function() {
  return this.value >= this.max;
}}}